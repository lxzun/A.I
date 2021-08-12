# Convolutional Auto Encoder --- for Understanding FCN Architecture 

# ANN구조의 AE -> CNN 구조의 CAE
# Decoder : Deconvolution 연산을 통해 data reconstruction !
# Deconvolution with torch.nn.ConvTranspose2d

# Module import 

# torch
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.init as init            # for weight , bias initialization
import torch.nn.functional as F
import torchvision.datasets as dsets # for MNIST dataset 
import torchvision.transforms as transforms # for tensor transforms 

from torch.utils.data import DataLoader # for batch learning

# others 
import numpy as np
import matplotlib.pyplot as plt


# MNIST dataset load
mnist_train = dsets.MNIST("MNIST_DATA/", train = True, transform = transforms.ToTensor(), download = True)
mnist_test = dsets.MNIST("MNIST_DATA/", train = False, transform = transforms.ToTensor(), download = True)

# Hyperparameter
training_epochs = 10
batch_size = 100
learning_rate = 0.1

# Dataloder
train_loader = DataLoader(dataset = mnist_train, batch_size=batch_size, shuffle = True, drop_last = True)
test_loader = DataLoader(dataset = mnist_test, batch_size=batch_size, shuffle = True, drop_last = True)

# Model Architecture 
class Encoder(nn.Module): # Convolution
    def __init__(self):
        super().__init__()
        self.layer1 = nn.Sequential(
            
            nn.Conv2d(1, 16, 3, padding = 1) # batch x 16 x 28 x 28
            nn.ReLU(),
            nn.BatchNorm2d(16),
            nn.Conv2d(16, 32, 3, padding = 1), # batch x 32 x 28 x 28
            nn.ReLU(),
            nn.BatchNorm2d(32),            
            nn.Conv2d(32, 64, 3, padding = 1), # batch x 64 x 28 x 28
            nn.ReLU(),
            nn.BatchNorm2d(64),            
            nn.MaxPool2d(2,2)                # batch x 64 x 14 x 14
            
        )
        self.layer2 = nn.Sequential(
            
            nn.Conv2d(64, 128, 3, padding = 1), # batch x 128 x 14 x 14
            nn.ReLU(),
            nn.BatchNorm(128),
            nn.MaxPool2d(2,2),                   # batch x 128 x 7 x 7
            nn.Conv2d(128, 256, 3, padding = 1), # batch x 256 x 7 x 7 
            nn.ReLU()        
            
        )
        
    def forward(self, x):
        z = layer1(x)
        z = layer2(z)
        out = z.view(batch_size, -1)  # latent space vector로써 1차원 tensor로 
        return out
        
    
# ******************************* Deconvolution *********************************** #

class Decoder(nn.Module): # Deconvolution
    def __init__(self):
        super().__init__()    
        self.layer1 = nn.Sequential(
            
            # nn.ConvTranspose2d(in-channel, out-channel, kernel, stide, padding, output-padding, ...)
            # padding 추가시, outline padding 크기 만큼 제거 
            
            # ( batch x 256 x 7 x 7 ) -> ( batch x 128 x 14 x 14 ) # 크기 증가
            nn.ConvTranspose2d(256, 128, 3, 2, 1, 1), 
            nn.ReLU(),
            nn.BatchNorm2d(128),
            nn.ConvTranspose2d(128, 64, 3, 1, 1),    #  batch x 64 x 14 x 14 
            nn.ReLU(),
            nn.BatchNorm2d(64)
        
        )
        
        self.layer2 = nn.Sequential(
        
            nn.ConvTranspose2d(64, 16, 3, 1, 1), # batch x 16 x 14 x 14 
            nn.ReLU(),
            nn.BatchNorm2d(16),
            nn.ConvTranspose2d(16, 1, 3, 2, 1, 1), # batch x 1 x 28 x 28 # 크기 증가
            nn.ReLU()
            
        )
    
    def forward(self, x):
        x = x.view(batch_size, 257, 7, 7)
        out = self.layer1(x)
        out = self.layer2(out)
        
        return out # batch x 1 x 28 x 28
      
      
      
# Model 객체 생성, optimizer, loss function 
encoder = Encoder()
decoder = Decoder()

# encoder와 decoder의 parameter를 모두 학습해야한다
# 다음과 같은 방식으로 묶어서 Optimizer에 넣어주면 된다!

parameters = list(encoder.parameters()) + list(decoder.parameters())
optimizer = optim.SGD(parameters, lr = learning_rate)
loss_func = nn.MSELoss() # pixel wise 계산할 것 


for epoch in range(training_epochs):
    for x, y, in train_loader:
        
        out = encoder(x)
        out = decoder(out)
        
        optimizer.zero_grad()
        loss = loss_func(out, x)
        
        loss.backward()
        optimizer.step()
            
    print(loss)
               

# Input - Output 이미지 비교 확인
plt.subplot(1,2,1)
plt.imshow(torch.squeeze(out.data[1]).numpy() , cmap = 'gray')
plt.subplot(1,2,2)
plt.imshow(torch.squeeze(x.data[1]).numpy(), cmap = 'gray')
plt.show()

# 참고 링크 https://wjddyd66.github.io/pytorch/Pytorch-AutoEncoder/


