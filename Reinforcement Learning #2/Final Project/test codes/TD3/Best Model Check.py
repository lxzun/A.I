# Noise 여러 개
# Q Network는 Only 1개 ...
# Best Action Choice 삭제 Only Softmax Choice
###########################################################################
# To Avoid Library Collision
import os

os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
###########################################################################
import gym
import sys
import copy
import random
import collections
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from time import sleep
from collections import deque
import matplotlib.pyplot as plt

#GPU Setting
device = 'cuda' if torch.cuda.is_available() else 'cpu'

print("")
print(f"On {device}")
print("")

class ReplayBuffer():
    def __init__(self):
        self.buffer = collections.deque(maxlen=buffer_limit)

    def put(self, transition):
        self.buffer.append(transition) # transition : (state, action, reward, next_state, done)

    def sample(self, n):
        mini_batch = random.sample(self.buffer, n) # buffer에서 n개 뽑기
        s_lst, a_lst, r_lst, s_prime_lst, done_mask_lst = [], [], [], [], []

        for transition in mini_batch:
            s, a, r, s_prime, done = transition
            s_lst.append(s) # s = [COS SIN 각속도]
            a_lst.append(a)
            r_lst.append([r])
            s_prime_lst.append(s_prime)
            done_mask = 0.0 if done else 1.0
            done_mask_lst.append([done_mask])

        s_lst = np.array(s_lst)
        a_lst = np.array(a_lst)
        r_lst = np.array(r_lst)
        s_prime_lst = np.array(s_prime_lst)
        done_mask_lst = np.array(done_mask_lst)

        return torch.tensor(s_lst, device = device, dtype=torch.float), torch.tensor(a_lst, device = device, dtype=torch.float), \
               torch.tensor(r_lst, device = device,dtype=torch.float), torch.tensor(s_prime_lst, device = device, dtype=torch.float), \
               torch.tensor(done_mask_lst, device = device, dtype=torch.float)

    def size(self):
        return len(self.buffer)


class MuNet1(nn.Module):  # Output : Deterministic Action !
    def __init__(self):
        super(MuNet1, self).__init__()
        self.fc1 = nn.Linear(24, 256) # Input  : 24 continuous states
        self.fc2 = nn.Linear(256, 256)
        self.fc_mu = nn.Linear(256, 4) # Output : 4 continuous actions

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        mu = torch.tanh(self.fc_mu(x))
        return mu



class QNet1(nn.Module):
    def __init__(self):
        super(QNet1, self).__init__()
        self.fc_sA   = nn.Linear(24, 128)    # State  24 개
        self.fc_aA   = nn.Linear(4, 128)     # Action 4  개
        self.fc_qA   = nn.Linear(256, 256)   # State , Action 이어붙이기
        self.fc_outA = nn.Linear(256, 1)     # Output : Q value

        self.fc_sB   = nn.Linear(24, 128)    # State  24 개
        self.fc_aB   = nn.Linear(4, 128)     # Action 4  개
        self.fc_qB   = nn.Linear(256, 256)   # State , Action 이어붙이기
        self.fc_outB = nn.Linear(256, 1)     # Output : Q value


    def forward(self, x, a):
        h1A = F.relu(self.fc_sA(x))
        h2A = F.relu(self.fc_aA(a))
        catA = torch.cat([h1A, h2A], dim = 1)
        q1 = F.relu(self.fc_qA(catA))
        q1 = self.fc_outA(q1)

        h1B = F.relu(self.fc_sB(x))
        h2B = F.relu(self.fc_aB(a))
        catB = torch.cat([h1B, h2B], dim = 1)
        q2 = F.relu(self.fc_qB(catB))
        q2 = self.fc_outB(q2)
        return q1, q2


# Add Noise to deterministic action for improving exploration property
class OrnsteinUhlenbeckNoise:
    def __init__(self, mu):
        self.theta, self.dt, self.sigma = 0.1, 0.01, 0.1
        self.mu = mu
        self.x_prev = np.zeros_like(self.mu)

    def __call__(self):
        x = self.x_prev + self.theta * (self.mu - self.x_prev) * self.dt + \
            self.sigma * np.sqrt(self.dt) * np.random.normal(size=self.mu.shape)
        self.x_prev = x

        x = torch.tensor(x, device = device, dtype = torch.float)

        return x


# Update Network Priodically ...
def soft_update(net, net_target):
    with torch.no_grad():
        for param_target, param in zip(net_target.parameters(), net.parameters()):
            param_target.data.copy_(param_target.data * (1.0 - tau) + param.data * tau)

def train(episode, mu, mu_target, q, q_target, memory, q_optimizer, mu_optimizer, batch_size):
    states, actions, rewards, next_states, dones = memory.sample(batch_size)

    with torch.no_grad():
        noise_bar  = torch.clamp(ou_noise(), -0.3, 0.3)
        next_action_bar = mu_target(next_states) + noise_bar

        target_q1, target_q2 = q_target(next_states, next_action_bar)
        target_q = torch.min(target_q1, target_q2)

        target_Q = rewards + (gamma*target_q*dones)

    current_q1, current_q2 = q(states, actions)

    loss1 = torch.nn.functional.mse_loss(current_q1, target_Q)
    loss2 = torch.nn.functional.mse_loss(current_q2, target_Q)

    Critic = loss1 + loss2
    q_optimizer.zero_grad()
    Critic.backward()
    q_optimizer.step()

    # Update Policy Network periodically ...
    if episode % 2 == 0:
        for p in q.parameters():
            p.requires_grad = False

        q_1, q_2 = q(states, mu(states))
        q_val = torch.min(q_1, q_2)

        mu_loss = (-q_val).mean()
        mu_optimizer.zero_grad()
        mu_loss.backward()
        mu_optimizer.step()

        soft_update(q, q_target)
        soft_update(mu, mu_target)

        for p in q.parameters():
            p.requires_grad = True


# Hyperparameters
gamma        = 0.99         # discount factor
buffer_limit = 100000      # Replay Memory Size
tau = 0.01                # for target network soft update

# Import Gym Environment
env = gym.make('BipedalWalker-v3')

# Replay Buffer
memory = ReplayBuffer()

# Networks
q1 =  QNet1().to(device) # Twin Network for avoiding maximization bias
q_target1 = copy.deepcopy(q1).eval().to(device)


mu1 = MuNet1().to(device)
mu2 = MuNet1().to(device)
mu3 = MuNet1().to(device)
mu4 = MuNet1().to(device)
mu5 = MuNet1().to(device)
mu_target1 = copy.deepcopy(mu1).eval().to(device)
mu_target2 = copy.deepcopy(mu2).eval().to(device)
mu_target3 = copy.deepcopy(mu3).eval().to(device)
mu_target4 = copy.deepcopy(mu4).eval().to(device)
mu_target5 = copy.deepcopy(mu5).eval().to(device)


for p in q_target1.parameters():
    p.requires_grad = False

for m in mu_target1.parameters():
    m.requires_grad = False
for m in mu_target2.parameters():
    m.requires_grad = False
for m in mu_target3.parameters():
    m.requires_grad = False
for m in mu_target4.parameters():
    m.requires_grad = False
for m in mu_target5.parameters():
    m.requires_grad = False


# Optimizer
mu_optimizer1 = optim.Adam(mu1.parameters(), lr=0.0009)
mu_optimizer2 = optim.Adam(mu2.parameters(), lr=0.0005)
mu_optimizer3 = optim.Adam(mu3.parameters(), lr=0.0003)
mu_optimizer4 = optim.Adam(mu4.parameters(), lr=0.0001)
mu_optimizer5 = optim.Adam(mu5.parameters(), lr=0.009)


q_optimizer1  = optim.Adam(q1.parameters(), lr=0.001)


# Noise
ou_noise = OrnsteinUhlenbeckNoise(mu=np.zeros(4))

score = 0.0
avg   = 0.0
avg_history       = []
reward_history_20 = []
MAX_EPISODES = 500
DECAYING_RATE = 2

for episode in range(MAX_EPISODES):
    state = env.reset()
    done  = False
    score = 0.0
    while not done: # Stacking Experiences

        DECAY = DECAYING_RATE - episode * 0.01
        if DECAY < 0:
            DECAY = 0
        state = torch.from_numpy(state).float().to(device)

        noise1 = ou_noise() * DECAY
        noise2 = ou_noise() * DECAY
        noise3 = ou_noise() * DECAY
        noise4 = ou_noise() * DECAY
        noise5 = ou_noise() * DECAY

        with torch.no_grad():
            action1 = mu1(state) + noise1
            action2 = mu2(state) + noise2
            action3 = mu3(state) + noise3
            action4 = mu4(state) + noise4
            action5 = mu5(state) + noise5

            q_value_for_softmax1 = q1(state.unsqueeze(0), action1.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax2 = q1(state.unsqueeze(0), action2.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax3 = q1(state.unsqueeze(0), action3.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax4 = q1(state.unsqueeze(0), action4.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax5 = q1(state.unsqueeze(0), action5.unsqueeze(0))[0][0].unsqueeze(0)

        # Voting
        actions = torch.stack([q_value_for_softmax1, q_value_for_softmax2, q_value_for_softmax3, q_value_for_softmax4, q_value_for_softmax5])
        action_softmax = torch.nn.functional.softmax(actions, dim=0).squeeze(1).squeeze(1)

        action_list = [action1, action2, action3, action4, action5]
        action_index = [0, 1, 2, 3, 4]

        choice_action = np.random.choice(action_index, 1, p=action_softmax.cpu().detach().numpy())

        # Noise가 사라지면, 대부분 Deterministic하게 Best Action을 선택할 것
        action = action_list[choice_action[0]].cpu().detach().numpy()

        next_state, reward, done, info = env.step(action)
        memory.put((state.cpu().numpy(), action, reward * 15, next_state, done))
        score = score + reward
        state = next_state

        if memory.size() > 2000:
            for i in range(5):
                train(episode, mu1, mu_target1, q1, q_target1, memory, q_optimizer1, mu_optimizer1, batch_size = 100)
                train(episode, mu2, mu_target2, q1, q_target1, memory, q_optimizer1, mu_optimizer2, batch_size = 100)
                train(episode, mu3, mu_target3, q1, q_target1, memory, q_optimizer1, mu_optimizer3, batch_size = 100)
                train(episode, mu4, mu_target4, q1, q_target1, memory, q_optimizer1, mu_optimizer4, batch_size = 100)
                train(episode, mu5, mu_target5, q1, q_target1, memory, q_optimizer1, mu_optimizer5, batch_size = 100)

    # Moving Average Count
    reward_history_20.append(score)

    if len(reward_history_20) > 10:
        avg = sum(reward_history_20[-10:]) / 10
        avg_history.append(avg)
    if episode % 10 == 0:
        print('episode: {} | reward: {:.1f} | 10 avg: {:.1f} '.format(episode, score, avg))
    episode += 1

env.close()

avg_history = np.array(avg_history)
reward_history_20 = np.array(reward_history_20)
np.save("./Rewards", reward_history_20)
np.save("./Best Model Check", avg_history)
