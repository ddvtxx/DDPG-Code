import torch as T
import torch.nn.functional as F
import numpy as np
from DDPG_network import ActorNetwork, CriticNetwork
from ReplayBuffer import ReplayBuffer

device = T.device("cuda:0" if T.cuda.is_available() else "cpu")


class DDPG:
    def __init__(self, alpha, beta, numSenario, numAPuser, numRU, 
                 actor_fc1_dim, actor_fc2_dim, actor_fc3_dim, actor_fc4_dim, 
                 critic_fc1_dim, critic_fc2_dim, critic_fc3_dim, critic_fc4_dim,  
                 ckpt_dir,
                 gamma=0.99, tau=0.005, action_noise=0.1, max_size=1000000,
                 batch_size=128):
        
        self.gamma = gamma
        self.tau = tau
        self.action_noise = action_noise
        self.checkpoint_dir = ckpt_dir

        self.actor = ActorNetwork(alpha=alpha, state_dim=numSenario*numAPuser*numRU, action_dim=numSenario*numAPuser*numRU,
                                  fc1_dim=actor_fc1_dim, fc2_dim=actor_fc2_dim,
                                  fc3_dim=actor_fc3_dim, fc4_dim=actor_fc4_dim)
        self.target_actor = ActorNetwork(alpha=alpha, state_dim=numSenario*numAPuser*numRU, action_dim=numSenario*numAPuser*numRU,
                                         fc1_dim=actor_fc1_dim, fc2_dim=actor_fc2_dim,
                                         fc3_dim=actor_fc3_dim, fc4_dim=actor_fc4_dim)
        self.critic = CriticNetwork(beta=beta, state_dim=numSenario*numAPuser*numRU, action_dim=numSenario*numAPuser*numRU,
                                    fc1_dim=critic_fc1_dim, fc2_dim=critic_fc2_dim,
                                    fc3_dim=critic_fc3_dim, fc4_dim=critic_fc4_dim)
        self.target_critic = CriticNetwork(beta=beta, state_dim=numSenario*numAPuser*numRU, action_dim=numSenario*numAPuser*numRU,
                                           fc1_dim=critic_fc1_dim, fc2_dim=critic_fc2_dim,
                                           fc3_dim=critic_fc3_dim, fc4_dim=critic_fc4_dim)

        self.memory = ReplayBuffer(max_size=max_size, numSenario=numSenario,
                                   numAPuser=numAPuser, numRU=numRU,
                                   batch_size=batch_size)

        # self.update_network_parameters(tau=1.0)
        self.update_network_parameters(self.tau)

        self.critic_loss_show = 0
        self.actor_loss_show = 0
        self.critic_value_show = 0
        self.target_show = 0

    def change_act_tau(self, act_tau):
        self.actor.change_tau(act_tau)
        self.target_actor.change_tau(act_tau)
        
    def update_network_parameters(self, tau=None):
        if tau is None:
            tau = self.tau

        for actor_params, target_actor_params in zip(self.actor.parameters(),
                                                     self.target_actor.parameters()):
            target_actor_params.data.copy_(tau * actor_params + (1 - tau) * target_actor_params)

        for critic_params, target_critic_params in zip(self.critic.parameters(),
                                                       self.target_critic.parameters()):
            target_critic_params.data.copy_(tau * critic_params + (1 - tau) * target_critic_params)

    def remember(self, state, action, reward, state_, done):
        self.memory.store_transition(state, action, reward, state_, done)

    def choose_action(self, observation, train=True):
        self.actor.eval()
        state = T.tensor(np.array([observation]), dtype=T.float).to(device)
        action = self.actor.forward(state).squeeze()

        if train:
            noise = T.tensor(np.random.normal(loc=0.0, scale=self.action_noise),
                             dtype=T.float).to(device)
            action = T.clamp(action+noise, 1e-15, 1)
        self.actor.train()

        return action.detach().cpu().numpy()

    def learn(self):
        if not self.memory.ready():
            return

        states, actions, reward, states_, terminals = self.memory.sample_buffer()
        states_tensor = T.tensor(states, dtype=T.float).to(device)
        actions_tensor = T.tensor(actions, dtype=T.float).to(device)
        rewards_tensor = T.tensor(reward, dtype=T.float).to(device)
        next_states_tensor = T.tensor(states_, dtype=T.float).to(device)
        terminals_tensor = T.tensor(terminals).to(device)

        with T.no_grad():
            next_actions_tensor = self.target_actor.forward(next_states_tensor)
            q_ = self.target_critic.forward(next_states_tensor, next_actions_tensor).view(-1)
            q_[terminals_tensor] = 0.0
            target = rewards_tensor + self.gamma * q_
        q = self.critic.forward(states_tensor, actions_tensor).view(-1)
    
        critic_loss = F.mse_loss(q, target.detach())
        
        self.critic.optimizer.zero_grad()
        critic_loss.backward()
        
        self.critic.optimizer.step()

        new_actions_tensor = self.actor.forward(states_tensor)
        actor_loss = -T.mean(self.critic.forward(states_tensor, new_actions_tensor)) ##### ????

        self.actor.optimizer.zero_grad()
        actor_loss.backward()

        self.actor.optimizer.step()
        
        self.critic_loss_show = critic_loss.detach().cpu().numpy() ##############################
        self.actor_loss_show = actor_loss.detach().cpu().numpy() ################################
        self.critic_value_show = q #######################################
        self.target_show = target #######################################
        
        self.update_network_parameters()
    
    def get_critic_loss(self):
        return self.critic_loss_show
    
    def get_actor_loss(self):
        return self.critic_loss_show
    
    def save_models(self, episode):
        self.actor.save_checkpoint(self.checkpoint_dir + 'Actor/DDPG_actor_{}.pth'.format(episode))
        print('Saving actor network successfully!')
        self.target_actor.save_checkpoint(self.checkpoint_dir +
                                          'Target_actor/DDPG_target_actor_{}.pth'.format(episode))
        print('Saving target_actor network successfully!')
        self.critic.save_checkpoint(self.checkpoint_dir + 'Critic/DDPG_critic_{}'.format(episode))
        print('Saving critic network successfully!')
        self.target_critic.save_checkpoint(self.checkpoint_dir +
                                           'Target_critic/DDPG_target_critic_{}'.format(episode))
        print('Saving target critic network successfully!')

    def load_models(self, episode):
        self.actor.load_checkpoint(self.checkpoint_dir + 'Actor/DDPG_actor_{}.pth'.format(episode))
        print('Loading actor network successfully!')
        self.target_actor.load_checkpoint(self.checkpoint_dir +
                                          'Target_actor/DDPG_target_actor_{}.pth'.format(episode))
        print('Loading target_actor network successfully!')
        self.critic.load_checkpoint(self.checkpoint_dir + 'Critic/DDPG_critic_{}'.format(episode))
        print('Loading critic network successfully!')
        self.target_critic.load_checkpoint(self.checkpoint_dir +
                                           'Target_critic/DDPG_target_critic_{}'.format(episode))
        print('Loading target critic network successfully!')