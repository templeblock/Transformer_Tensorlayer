import tensorflow as tf
import tensorlayer as tl
import numpy as np
import argparse
from utils.tokenizer import *
from models import model_params
from models.transformer_v4 import Transformer
from utils.pipeline_dataset import train_input_fn
from utils import metrics
from models import optimizer
from translate_file import translate_file
from utils import tokenizer
from compute_bleu import bleu_wrapper
import time


_TARGET_VOCAB_SIZE = 32768  # Number of subtokens in the vocabulary list.
_TARGET_THRESHOLD = 327  # Accept vocabulary if size is within this threshold
VOCAB_FILE = "vocab.ende.%d" % _TARGET_VOCAB_SIZE

class CustomSchedule(tf.keras.optimizers.schedules.LearningRateSchedule):
  def __init__(self, d_model, warmup_steps=5):
    super(CustomSchedule, self).__init__()
    
    self.d_model = d_model
    self.d_model = tf.cast(self.d_model, tf.float32)

    self.warmup_steps = warmup_steps
    
  def __call__(self, step):
    arg1 = tf.math.rsqrt(step)
    arg2 = step * (self.warmup_steps ** -1.5)
    
    return tf.math.rsqrt(self.d_model) * tf.math.minimum(arg1, arg2)




def train_model(input_params):
    params = model_params.EXAMPLE_PARAMS_v4
    dataset = train_input_fn(input_params)
    subtokenizer = tokenizer.Subtokenizer("data/data/"+VOCAB_FILE)
    input_file = "data/raw/dev/newstest2013.en"
    output_file = "./output/dev.de"

    ref_filename = "data/raw/dev/newstest2013.de"
    trace_path = "checkpoints_v4/logging/"
    num_epochs = 10
    

    def train_step(inputs, targets):
        model.train()
        with tf.GradientTape() as tape:
            #print(inputs)
            
            logits = model(inputs=inputs, targets=targets)
            logits = metrics.MetricLayer(params.vocab_size)([logits, targets])
            logits, loss = metrics.LossLayer(params.vocab_size, 0.1)([logits, targets])

            
        gradients = tape.gradient(loss, model.all_weights)
        optimizer_.apply_gradients(zip(gradients, model.all_weights))
        return loss

    
    model = Transformer(params)
    # load_weights = tl.files.load_npz(name='./checkpoints_v4/model.npz')
    # tl.files.assign_weights(load_weights, model)
    learning_rate = CustomSchedule(params.hidden_size, warmup_steps=params.learning_rate_warmup_steps)
    optimizer_ = optimizer.LazyAdam(learning_rate, beta_1=0.9, beta_2=0.98, epsilon=1e-9)
    
    time_ = time.time()
    for epoch in range(num_epochs):
        total_loss, n_iter = 0, 0
        for i, [inputs, targets] in enumerate(dataset):
            loss = train_step(inputs, targets)
            with tf.io.gfile.GFile(trace_path+"loss", "ab+") as trace_file:
                trace_file.write(str(loss.numpy())+'\n')
            if (i % 100 == 0):
                print('Batch ID {} at Epoch [{}/{}]: loss {:.4f} using {:.4f}'.format(i, epoch + 1, num_epochs, loss, (time.time()-time_)/100))
                time_ = time.time()
            if (i % 2000 == 0):
                tl.files.save_npz(model.all_weights, name='./checkpoints_v4/model.npz')
            if (i == 5000):
                translate_file(model, subtokenizer, input_file=input_file, output_file=output_file)
                try:
                    insensitive_score = bleu_wrapper(ref_filename, output_file, False)
                    sensitive_score = bleu_wrapper(ref_filename, output_file, True)
                    with tf.io.gfile.GFile(trace_path+"bleu_insensitive", "ab+") as trace_file:
                        trace_file.write(str(insensitive_score)+'\n')
                    with tf.io.gfile.GFile(trace_path+"bleu_sensitive", "ab+") as trace_file:
                        trace_file.write(str(sensitive_score)+'\n')   
                except:
                    print("An exception occurred")
         
            total_loss += loss
            n_iter += 1

        # printing average loss after every epoch
        print('Epoch [{}/{}]: loss {:.4f}'.format(epoch + 1, num_epochs, total_loss / n_iter))
        # save model weights after every epoch
        tl.files.save_npz(model.all_weights, name='./checkpoints_v4/model.npz')






if __name__ == '__main__':

    params = {}
    params["batch_size"] = 2048
    params["max_length"] = 256
    params["num_parallel_calls"] = 1
    params["repeat_dataset"] = 1
    params["static_batch"] = False
    params["num_gpus"] = 2
    params["use_synthetic_data"] = False
    params["data_dir"] = './data/data/wmt32k-train*'
    train_model(params)
