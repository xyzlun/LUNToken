#coding='utf-8'
import hashlib
import json
import request
from textwrap import dedent
from urllib import parse
from time import time
from uuid import uuid4
from flask import Flask,jsonify,request

class Blockchain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()  # 使用set储存节点
        # create the genesis block
        self.new_block(previous_hash=1,proof=100)

    def register_node(self,address):
        '''
        add a new node to the list of nodes
        :param address: <str> address of node. eg:'http://192.168.0.5:5000'
        :return: None
        '''
        parsed_url = parse.urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def new_block(self,proof,previous_hash=None):
        # create a new block and adds it to the chain
        """
        生成新块
        :param proof: <int> the proof given by the proof of work algorithm
        :param previous_hash: (optional)<str> hash of previous block
        :return: <dict> new block
        """
        block = {
            'index' : len(self.chain) + 1,
            'timestamp' : time(),
            'transactions' : self.current_transactions,
            'proof' : proof,
            'previous_hash' : previous_hash or self.hash(self.chain[-1]),
        }
        # reset the current list of transactions
        self.current_transactions = []
        self.chain.append(block)
        return block
    def new_transaction(self,sender,recipient,amount):
        # add a new transaction to the list of transactions
        """
        生成新交易信息，信息将加入到下一个待挖的区块中
        :param sender:<str> address of the sender
        :param recipient:<str> address of the recipient
        :param amount:<int> amount
        :return:<int> the index of the block that will hold this transaction
        """
        self.current_transactions.append({
            'sender':sender,
            'recipient':recipient,
            'amount':amount,
        })
        return self.last_block['index'] + 1

    # 共识算法
    def valid_chain(self,chain):  # 检查是否是有效链，遍历每个块验证hash和proof.
        '''
        determine if a given blockchain is valid
        :param chain: <list> a blockchain
        :return: <bool> true if valid,false if not
        '''
        last_block = chain[0]
        current_index = 1
        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n------------\n")
            # check that the hash of the block is correct
            if block['previous_hash'] != self.hash(last_block):
                return False
            # check that the proof of work is correct
            if not self.valid_proof(last_block['proof'],block['proof']):
                return False
            last_block = block
            current_index += 1
        return True

    def resolve_conflicts(self):  # 遍历所有的邻居节点，并检查链的有效性， 如果发现有效更长链，就替换掉自己的链。
        """
        共识算法解决冲突
        使用网络中最长的链
        :return: <bool> True如果链被取代，否则为False
        """
        neighbours = self.nodes
        new_chain = None
        # we're only looking for chains longer than ours
        max_length = len(self.chain)
        # grab and verify the chains from all the nodes in our network
        for node in neighbours:
            response = request.get(f'http://{node}/chain')
            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']
                # check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain
        # replace our chain if we discovered a new,valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True
        return False

    @staticmethod
    def hash(block):
        # hash a block
        """
        生成块的SHA-256 hash 值
        :param block:<dict> block
        :return: <str>
        """
        # we must make sure that the dictionary is ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block,sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()
    @property
    def last_block(self):
        # return the last block in the chain
        return self.chain[-1]

    def proof_of_work(self,last_proof):
        """
        简单的工作量证明：
        -查找一个p'使得hash(pp')以4个0开头
        -p是上一个块的证明，p'是当前的证明
        :param last_proof: <int>
        :return: <int>
        """
        proof = 0
        while self.valid_proof(last_proof,proof) is False:
            proof += 1
        return proof
    @staticmethod
    def valid_proof(last_proof,proof):
        """
        验证证明：是否hash(last_proof,proof)以4个0开头
        :param last_proof: <int> previous proof
        :param proof: <int> current proof
        :return: <bool> true if correct, false if not
        """
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[ :4 ] == '0000'

# instantiate our Node
app = Flask(__name__)  # 创建一个节点
# generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-','')  # 为节点创建一个随机名字
# instantiate the blockchain
blockchain = Blockchain()  # 实例化blockchain类

@app.route('/mine',methods=['GET'])
def mine():  # 创建/mine GET接口  挖矿
    # we run the proof of work algorithm to get the next proof
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)
    # 给工作量证明的节点提供奖励
    # 发送者为"0"表明是新挖出的币
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )
    # forge the new block by adding it to the chain
    block = blockchain.new_block(proof)
    response = {
        'message' : "New Block Forge",
        'index' : block['index'],
        'transactions' : block['transactions'],
        'proof' : block['proof'],
        'previous_hash' : block['previous_hash'],
    }
    return jsonify(response),200

@app.route('/transactions/new',methods=['POST'])
def new_transaction():  # 创建/transaction/new POST接口，可以给接口发送交易数据
    values = request.get_json()
    # return jsonify(values)
    # check that the required field are in the POST'ed data
    required = ['sender','recipient','amount']
    if not all(k in values for k in required):
        return 'Missing values',400
    # create a new transaction
    index = blockchain.new_transaction(values['sender'],values['recipient'],values['amount'])
    response = {'message': f'Transaction will be added to Block{index}'}
    return jsonify(response),201

@app.route('/chain',methods=['GET'])
def full_chain():  # 创建/chain 接口，返回整个区块链
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response),200

@app.route('/nodes/register',methods=['POST'])
def register_nodes():
    values = request.get_json()
    nodes = values.get('nodes')
    if nodes is None:
        return 'Error: Please supply a valid list of nodes',400
    for node in nodes:
        blockchain.register_node(node)
    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response),201

@app.route('/nodes/resolve',methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()
    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }
    return jsonify(response),200

if __name__ == '__main__':
    app.run(host='127.0.0.1',port=5000)
    app.run(host='127.0.0.1',port=5001)