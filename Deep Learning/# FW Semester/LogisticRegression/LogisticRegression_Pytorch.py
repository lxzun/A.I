import torch 
from torch.autograd import Variable

# Tensor data
x_data = Variable(torch.Tensor([[1.0],[2.0],[3.0],[4.0]])) 
y_data = Variable(torch.Tensor([[0.],[0.],[1.],[1.]])) # 2. Binary Classification 이기 때문에 0 또는 1을 Label 값으로 갖는다.
 
# 1. 모델 디자인 with class
############################################################################################

class Model(torch.nn.Module):
    
    # 모델 초기설정
    def __init__(self):
        super(Model,self).__init__()
        self.linear = torch.nn.Linear(1,1) # 1 Input , 1 Output
        
    # Forward Pass
    def forward(self,x):
        y_pred = torch.nn.functional.sigmoid(self.linear(x)) # linear regression과 다르게 한 단계 더 거친다 (Activation function)
        return y_pred

model = Model()

# 2. Loss, Optimizer Setting
############################################################################################


criterion = torch.nn.BCELoss(size_average=False) # MSE Loss 대신 Binary Cross Entropy Loss function 사용
optimizer = torch.optim.SGD(model.parameters(), lr = 0.01)

# 3. Training Cycle : Forward, Backward, Update with loss and Optimizer
############################################################################################

for epoch in range(1000):
    
    # Forward Pass
    y_pred = model(x_data)
    
    # Compute loss and print 
    loss = criterion(y_pred, y_data) 
    print(epoch, loss.item())
    
    optimizer.zero_grad() # Gradient Initialize
    loss.backward()  # Backward Pass
    optimizer.step() # Update
    

# 1.0 Input data 생성 및 학습된 모델에 입력
hour_var = Variable(torch.tensor([[1.0]]))
print("predict 1 hour", 1.0, model(hour_var).data[0][0].item() > 0.5)

# 1.0 Input data 생성 및 학습된 모델에 입력
hour_var = Variable(torch.tensor([[7.0]]))
print("predict 7 hour", 7.0, model(hour_var).data[0][0].item() > 0.5)
