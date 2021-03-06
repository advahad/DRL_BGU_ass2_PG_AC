import gym
import numpy as np
import tensorflow as tf
import collections
import summary_util

env = gym.make('CartPole-v1')
env._max_episode_steps = None

np.random.seed(1)

# CONFIGURATIONS
V_NET_LAYER_SIZE = 20
POLICY_NET_LAYER_SIZE = 20

LOGS_PATH = './logs/advantage-PG'

# Define hyper parameters
state_size = 4
action_size = env.action_space.n

max_episodes = 5000
max_steps = 5000
discount_factor = 0.99
learning_rate = 0.001
value_net_learning_rate = 0.01

render = False


class StateValueNetwork:
    def __init__(self, state_size, output_size, learning_rate, name='state_value_network'):
        self.state_size = state_size
        self.output_size = output_size
        self.learning_rate = learning_rate

        with tf.variable_scope(name):
            self.state = tf.placeholder(tf.float32, [None, self.state_size], name="state")
            self.total_reward = tf.placeholder(tf.int32, name="total_reward")
            self.A = tf.placeholder(tf.float32, name="advantage")

            self.W1 = tf.get_variable("W1", [self.state_size, 12],
                                      initializer=tf.contrib.layers.xavier_initializer(seed=0))
            self.b1 = tf.get_variable("b1", [12],
                                      initializer=tf.zeros_initializer())
            self.W2 = tf.get_variable("W2", [12, 1],
                                      initializer=tf.contrib.layers.xavier_initializer(seed=0))
            self.b2 = tf.get_variable("b2", [1],
                                      initializer=tf.zeros_initializer())

            self.Z1 = tf.add(tf.matmul(self.state, self.W1), self.b1)
            self.A1 = tf.nn.relu(self.Z1)
            self.Z2 = tf.add(tf.matmul(self.A1, self.W2), self.b2)
            self.value_estimate = tf.squeeze(self.Z2)

            # # Softmax probability distribution over actions
            # self.reward_expectation = tf.squeeze(tf.nn.li(self.output))
            # Loss with negative log probability
            # self.loss = self.A*self.value_estimate
            self.loss = tf.losses.mean_squared_error(self.value_estimate,
                                                     self.total_reward)  # the loss function
            # self.loss = tf.squared_difference(self.value_estimate, self.total_reward)
            # self.loss = tf.reduce_mean(self.value_estimate * self.A)
            self.optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(self.loss)


class PolicyNetwork:
    def __init__(self, state_size, action_size, learning_rate, name='policy_network'):
        self.state_size = state_size
        self.action_size = action_size
        self.learning_rate = learning_rate

        with tf.variable_scope(name):
            self.state = tf.placeholder(tf.float32, [None, self.state_size], name="state")
            self.action = tf.placeholder(tf.int32, [self.action_size], name="action")
            self.A = tf.placeholder(tf.float32, name="advantage")

            self.W1 = tf.get_variable("W1", [self.state_size, 12],
                                      initializer=tf.contrib.layers.xavier_initializer(seed=0))
            self.b1 = tf.get_variable("b1", [12], initializer=tf.zeros_initializer())
            self.W2 = tf.get_variable("W2", [12, self.action_size],
                                      initializer=tf.contrib.layers.xavier_initializer(seed=0))
            self.b2 = tf.get_variable("b2", [self.action_size], initializer=tf.zeros_initializer())

            self.Z1 = tf.add(tf.matmul(self.state, self.W1), self.b1)
            self.A1 = tf.nn.relu(self.Z1)
            self.output = tf.add(tf.matmul(self.A1, self.W2), self.b2)

            # Softmax probability distribution over actions
            self.actions_distribution = tf.squeeze(tf.nn.softmax(self.output))
            # Loss with negative log probability
            self.neg_log_prob = tf.nn.softmax_cross_entropy_with_logits(logits=self.output,
                                                                        labels=self.action)  # (y_hat, y)
            self.loss = tf.reduce_mean(self.neg_log_prob * self.A)
            self.optimizer = tf.train.AdamOptimizer(learning_rate=self.learning_rate).minimize(self.loss)


# Initialize the policy network
tf.reset_default_graph()

policy = PolicyNetwork(state_size, action_size, learning_rate)
state_value_network = StateValueNetwork(state_size, 1, value_net_learning_rate)

summary_writer = summary_util.init(LOGS_PATH)

# Start training the agent with REINFORCE algorithm
with tf.Session() as sess:
    sess.run(tf.global_variables_initializer())
    solved = False
    Transition = collections.namedtuple("Transition", ["state", "action", "reward", "next_state", "done"])
    episode_rewards = np.zeros(max_episodes)
    average_rewards = 0.0
    policy_losses = []
    value_losses = []

    for episode in range(max_episodes):
        state = env.reset()
        state = state.reshape([1, state_size])
        episode_transitions = []

        # generate episode (trajectory) following policy pai
        for step in range(max_steps):
            actions_distribution = sess.run(policy.actions_distribution, {policy.state: state})
            action = np.random.choice(np.arange(len(actions_distribution)), p=actions_distribution)
            next_state, reward, done, _ = env.step(action)
            next_state = next_state.reshape([1, state_size])

            if render:
                env.render()

            action_one_hot = np.zeros(action_size)
            action_one_hot[action] = 1
            episode_transitions.append(
                Transition(state=state, action=action_one_hot, reward=reward, next_state=next_state, done=done))
            episode_rewards[episode] += reward

            if done:
                if episode > 98:
                    # Check if solved
                    average_rewards = np.mean(episode_rewards[(episode - 99):episode + 1])
                print("Episode {} Reward: {} Average over 100 episodes: {}".format(episode, episode_rewards[episode],
                                                                                   round(average_rewards, 2)))
                if average_rewards > 475:
                    print(' Solved at episode: ' + str(episode))
                    solved = True
                break
            state = next_state

        if solved:
            break

        # Compute Rt for each time-step t and update the network's weights
        for t, transition in enumerate(episode_transitions):
            total_discounted_return = sum(
                discount_factor ** i * t.reward for i, t in enumerate(episode_transitions[t:]))  # Rt

            sess = sess or tf.get_default_session()
            total_discounted_return_estimate = sess.run(state_value_network.value_estimate,
                                                        {state_value_network.state: transition.state})

            A = total_discounted_return - total_discounted_return_estimate

            # update state value network
            state_value_feed_dict = {state_value_network.state: transition.state,
                                     state_value_network.total_reward: total_discounted_return,
                                     state_value_network.A: A}
            sess = sess or tf.get_default_session()
            _, state_value_loss = sess.run([state_value_network.optimizer, state_value_network.loss],
                                           state_value_feed_dict)
            value_losses.append(state_value_loss)

            # update policy network
            feed_dict = {policy.state: transition.state, policy.A: A,
                         policy.action: transition.action}
            sess = sess or tf.get_default_session()
            _, loss = sess.run([policy.optimizer, policy.loss], feed_dict)
            policy_losses.append(loss)

        # update and save tensorboared summaries
        policy_episode_summary = summary_util.create_avg_summary(policy_losses, "policy loss")
        value_episode_summary = summary_util.create_avg_summary(value_losses, "value loss")
        rewards_summary = summary_util.create_summary(episode_rewards[episode], "total rewards")
        summaries = [policy_episode_summary, value_episode_summary, rewards_summary]
        summary_util.write_summaries(summary_writer, episode, summaries)

    summary_writer.close()
