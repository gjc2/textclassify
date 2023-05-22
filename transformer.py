import torch
import torch.nn as nn
import math
import torch.optim as optim
import numpy as np
from torchtext.data.utils import get_tokenizer
import torchtext.datasets as datasets
from torchtext.vocab import build_vocab_from_iterator
from torchtext.transforms import Truncate, PadTransform
import torch.utils.data as Data
from tqdm import tqdm
import matplotlib.pyplot as plt

# 1 define network

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, vocab_size=5000, dropout=0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(vocab_size, d_model)
        position = torch.arange(0, vocab_size, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float()
            * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x):
        x = x + self.pe[:, : x.size(1), :]
        return self.dropout(x)



class Net(nn.Module):
    def __init__(self, vocab_size, embedding_dim, output_dim, n_head, n_layers):
        super(Net, self).__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim)
        self.pos_encoder = PositionalEncoding(
            d_model=embedding_dim,
            vocab_size=vocab_size
        )
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embedding_dim,
            batch_first=True,
            nhead = n_head,

        )
        self.transformer = nn.TransformerEncoder(encoder_layer, n_layers)
        self.fc = nn.Linear(embedding_dim, output_dim)

    def forward(self, text):
         text = self.embedding(text)
         text = self.pos_encoder(text)
         text = self.transformer(text)
         text = text.mean(dim=1)
         text = self.fc(text)
         return text


# 2 define parameter

VOCAB_SIZE = 0
EMBEDDING_DIM = 100
OUTPUT_DIM = 4
DROPOUT = 0.3
BATCH_SIZE = 64
N_HEAD = 2
N_LAYERS = 3

# 3 process data

tokenize = get_tokenizer("basic_english")


def yield_tokens(data):
    for _, text in data:
        yield tokenize(text)


train_set = datasets.AG_NEWS(root='.data', split='train')
test_set = datasets.AG_NEWS(root='.data', split='test')

vocab = build_vocab_from_iterator(
    yield_tokens(train_set), specials=["<pad>", "<unk>"]
)
vocab.set_default_index(vocab['<unk>'])
VOCAB_SIZE = len(vocab)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


def create_dataset(_set):
    label_list, text_list =[], []
    truncate = Truncate(max_seq_len=200)
    pad = PadTransform(max_length=200, pad_value=vocab['<pad>'])
    for (_label, _text) in _set:
        label_list.append([i+1 == _label for i in range(OUTPUT_DIM)])
        text = vocab(tokenize(_text))
        text = truncate(text)
        text = torch.tensor(text, dtype=torch.int64)
        text = pad(text)
        text_list.append(text)
    label_list = torch.tensor(label_list, dtype=torch.float)
    text_list = torch.vstack(text_list)
    return text_list.to(device), label_list.to(device)


input_data, input_label = create_dataset(train_set)
ag_news_train = Data.TensorDataset(input_data, input_label)

test_data, test_label = create_dataset(test_set)
ag_news_test = Data.TensorDataset(test_data, test_label)

train_loader = Data.DataLoader(ag_news_train, BATCH_SIZE, True, drop_last=True)
test_loader = Data.DataLoader(ag_news_test, BATCH_SIZE, True, drop_last=True)


# 4 create model

model = Net(VOCAB_SIZE, EMBEDDING_DIM, OUTPUT_DIM, N_HEAD, N_LAYERS).to(device)
criterion = nn.CrossEntropyLoss().to(device)
optimizer = optim.Adam(model.parameters())

# 5 train model


def accuracy(pred, label):
    _, pred = torch.max(pred, 1)
    _, label = torch.max(label, 1)
    correct = pred.detach().cpu().numpy() == label.detach().cpu().numpy()
    acc = np.sum(correct) / BATCH_SIZE
    return acc


def train(model, loader, optimizer, criterion):
    model.train()
    epoch_loss = 0
    epoch_acc = 0
    for batch_data, batch_label in tqdm(loader):
        pred = model(batch_data)
        # print(pred.shape) # [batch_size, 4]
        loss = criterion(pred, batch_label)
        acc = accuracy(pred, batch_label)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        epoch_acc += acc.item()
        epoch_loss += loss.item()
    return epoch_loss / len(loader), epoch_acc / len(loader)


def evaluate(model, loader, criterion):
    model.eval()
    epoch_loss = 0
    epoch_acc = 0
    with torch.no_grad():
        for batch_data, batch_label in tqdm(loader):
            pred = model(batch_data)
            loss = criterion(pred, batch_label)
            acc = accuracy(pred, batch_label)
            epoch_loss += loss.item()
            epoch_acc += acc.item()
    return epoch_loss / len(loader), epoch_acc / len(loader)


N_EPOCHS = 10


def train_model():
    best_valid_loss = float('inf')
    train_l, train_a, test_l, test_a = [], [], [], []
    for epoch in range(N_EPOCHS):
        train_loss, train_acc = train(model, train_loader, optimizer, criterion)
        valid_loss, valid_acc = evaluate(model, test_loader, criterion)
        train_l.append(train_loss)
        train_a.append(train_acc)
        test_l.append(valid_loss)
        test_a.append(valid_acc)
        if valid_loss < best_valid_loss:
            best_valid_loss = valid_loss
            #torch.save(model.state_dict(), f'checkpoints/linear/linear_model_{epoch}.pt')
        print(
            f'Epoch : {epoch + 1}, train_loss :{train_loss} ,train_acc = {train_acc}, test_loss:{valid_loss}, test_acc={valid_acc}')
    plt.figure
    plt.title('transformer')
    plt.xlabel('epoch')
    plt.ylabel('loss/acc')
    plt.plot([x for x in range(len(train_l))], train_l, 'r-', label="train_loss")
    plt.plot([x for x in range(len(train_a))], train_a, 'b-.', label="train_acc")
    plt.plot([x for x in range(len(test_l))], test_l, 'g-', label="valid_loss")
    plt.plot([x for x in range(len(test_a))], test_a, 'y-.', label="valid_acc")
    plt.legend()
    plt.savefig('transformer.png', dpi=1000, bbox_inches='tight')
    plt.show()
# model.load_state_dict(torch.load('/'))


if __name__ == '__main__':
    train_model()
