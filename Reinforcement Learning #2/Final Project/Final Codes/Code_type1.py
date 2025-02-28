'''

Critic x 1
Actor x 8

'''
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

# GPU Setting
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


# Type 1에서는 동일한 Actor를 8개 사용합니다.
class MuNet1(nn.Module):
    def __init__(self):
        super(MuNet1, self).__init__()
        self.fc1 = nn.Linear(24, 256)  # Input  : 24 continuous states
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

        '''
        TD3 Network를 위해 2개의 Newtork를 생성합니다. 
        '''
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


# Exploration property를 추가하기 위해 노이즈를 생성합니다. (Gaussian or Uniform Noise도 OK)
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

    # Implement Basic TD3 Algorithm
    with torch.no_grad():

        # Noise Clamping
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

    # Update Policy Network periodically...
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
buffer_limit = 100000       # Replay Memory Size
tau = 0.01                  # for target network soft update

# Import Gym Environment
env = gym.make('BipedalWalker-v3')

# Replay Buffer
memory = ReplayBuffer()

# Networks
q1 =  QNet1().to(device) # Twin Network for avoiding maximization bias
q_target1 = copy.deepcopy(q1).eval().to(device) # Parameter Synchronize


# 8개의 동일한 Actor Network 생성
mu1 = MuNet1().to(device)
mu2 = MuNet1().to(device)
mu3 = MuNet1().to(device)
mu4 = MuNet1().to(device)
mu5 = MuNet1().to(device)
mu6 = MuNet1().to(device)
mu7 = MuNet1().to(device)
mu8 = MuNet1().to(device)
mu_target1 = copy.deepcopy(mu1).eval().to(device) # Parameter Synchronize
mu_target2 = copy.deepcopy(mu2).eval().to(device) # Parameter Synchronize
mu_target3 = copy.deepcopy(mu3).eval().to(device) # Parameter Synchronize
mu_target4 = copy.deepcopy(mu4).eval().to(device) # Parameter Synchronize
mu_target5 = copy.deepcopy(mu5).eval().to(device) # Parameter Synchronize
mu_target6 = copy.deepcopy(mu6).eval().to(device) # Parameter Synchronize
mu_target7 = copy.deepcopy(mu7).eval().to(device) # Parameter Synchronize
mu_target8 = copy.deepcopy(mu8).eval().to(device) # Parameter Synchronize

# Target Network Gradient 계산 중지
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
for m in mu_target6.parameters():
    m.requires_grad = False
for m in mu_target7.parameters():
    m.requires_grad = False
for m in mu_target8.parameters():
    m.requires_grad = False

# Optimizer 생성 및 하이퍼파라미터 튜닝
mu_optimizer1 = optim.Adam(mu1.parameters(), lr=0.0009)
mu_optimizer2 = optim.Adam(mu2.parameters(), lr=0.0005)
mu_optimizer3 = optim.Adam(mu3.parameters(), lr=0.0003)
mu_optimizer4 = optim.Adam(mu4.parameters(), lr=0.0001)
mu_optimizer5 = optim.Adam(mu5.parameters(), lr=0.009)
mu_optimizer6 = optim.Adam(mu6.parameters(), lr=0.005)
mu_optimizer7 = optim.Adam(mu7.parameters(), lr=0.003)
mu_optimizer8 = optim.Adam(mu8.parameters(), lr=0.001)

q_optimizer1  = optim.Adam(q1.parameters(), lr=0.001)

# Noise
ou_noise = OrnsteinUhlenbeckNoise(mu=np.zeros(4))

MAX_EPISODES = 500
DECAYING_RATE = 2      # For Decaying Noise

avg_history       = [] # Average Reward List
reward_history_20 = [] # Reward List
softmax_recores   = [] # Softmax Value List
time_step = 0          # Count time step for Softmax Value
score = 0.0

for episode in range(MAX_EPISODES):
    state = env.reset()
    done  = False
    score = 0.0
    while not done:

        # 100 ~ 150사이의 Episode에서 Noise 사라지도록
        DECAY = DECAYING_RATE - episode * 0.01
        if DECAY < 0:
            DECAY = 0
        state = torch.from_numpy(state).float().to(device)

        # 8개의 Noise 생성
        noise1 = ou_noise() * DECAY
        noise2 = ou_noise() * DECAY
        noise3 = ou_noise() * DECAY
        noise4 = ou_noise() * DECAY
        noise5 = ou_noise() * DECAY
        noise6 = ou_noise() * DECAY
        noise7 = ou_noise() * DECAY
        noise8 = ou_noise() * DECAY

        with torch.no_grad():

            # 8개의 Action + Noise
            action1 = mu1(state) + noise1
            action2 = mu2(state) + noise2
            action3 = mu3(state) + noise3
            action4 = mu4(state) + noise4
            action5 = mu5(state) + noise5
            action6 = mu6(state) + noise6
            action7 = mu7(state) + noise7
            action8 = mu8(state) + noise8

            # 8개의 Action에 대한 Q Value 계산
            q_value_for_softmax1 = q1(state.unsqueeze(0), action1.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax2 = q1(state.unsqueeze(0), action2.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax3 = q1(state.unsqueeze(0), action3.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax4 = q1(state.unsqueeze(0), action4.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax5 = q1(state.unsqueeze(0), action5.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax6 = q1(state.unsqueeze(0), action6.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax7 = q1(state.unsqueeze(0), action7.unsqueeze(0))[0][0].unsqueeze(0)
            q_value_for_softmax8 = q1(state.unsqueeze(0), action8.unsqueeze(0))[0][0].unsqueeze(0)

        # Soft Voting
        actions = torch.stack([q_value_for_softmax1, q_value_for_softmax2, q_value_for_softmax3, q_value_for_softmax4, q_value_for_softmax5, q_value_for_softmax6, q_value_for_softmax7, q_value_for_softmax8])

        print(actions.shape)
        sys.exit()

        action_softmax = torch.nn.functional.softmax(actions, dim=0).squeeze(1).squeeze(1)

        # Soft max Converge Check - 분포가 어떻게 수렴하는지
        if time_step % 1000 == 0:
            softmax_recores.append(action_softmax.cpu().detach().numpy())
        time_step += 1

        # Soft Voting
        action_list = [action1, action2, action3, action4, action5, action6, action7, action8]
        action_index = [0, 1, 2, 3, 4, 5, 6, 7]
        choice_action = np.random.choice(action_index, 1, p=action_softmax.cpu().detach().numpy())

        # Noise가 사라지면, Deterministic하게 또는 Uniform하게 Optimal Action을 선택
        action = action_list[choice_action[0]].cpu().detach().numpy()

        next_state, reward, done, info = env.step(action)
        memory.put((state.cpu().numpy(), action, reward, next_state, done))
        score = score + reward
        state = next_state

        if memory.size() > 2000:
            for i in range(5):
                train(episode, mu1, mu_target1, q1, q_target1, memory, q_optimizer1, mu_optimizer1, batch_size = 100)
                train(episode, mu2, mu_target2, q1, q_target1, memory, q_optimizer1, mu_optimizer2, batch_size = 100)
                train(episode, mu3, mu_target3, q1, q_target1, memory, q_optimizer1, mu_optimizer3, batch_size = 100)
                train(episode, mu4, mu_target4, q1, q_target1, memory, q_optimizer1, mu_optimizer4, batch_size = 100)
                train(episode, mu5, mu_target5, q1, q_target1, memory, q_optimizer1, mu_optimizer5, batch_size = 100)
                train(episode, mu6, mu_target6, q1, q_target1, memory, q_optimizer1, mu_optimizer6, batch_size = 100)
                train(episode, mu7, mu_target7, q1, q_target1, memory, q_optimizer1, mu_optimizer7, batch_size = 100)
                train(episode, mu8, mu_target8, q1, q_target1, memory, q_optimizer1, mu_optimizer8, batch_size = 100)

    # Moving Average Count
    reward_history_20.append(score)
    if len(reward_history_20) > 10:
        avg = sum(reward_history_20[-10:]) / 10
        avg_history.append(avg)
    if episode % 10 == 0:
        print('episode: {} | reward: {:.1f} | 10 avg: {:.1f} '.format(episode, score, avg))
    episode += 1

env.close()

# Numpy array로 list 저장
avg_history = np.array(avg_history)
np.save("./type1", avg_history)
np.save("./Softmax type1", softmax_recores)

# Average Reward Plot
length = np.arange(len(avg_history))
plt.figure()
plt.xlabel("Episode")
plt.ylabel("10 episode MVA")
plt.plot(length, avg_history)
plt.savefig('type1.png')
