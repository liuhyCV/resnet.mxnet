import logging, os
import sys

import config

sys.path.insert(0, config.mxnet_path)
import mxnet as mx
from core.scheduler import multi_factor_scheduler
from core.solver import Solver
from data import *
from symbol import *


def main(config):
    # log file
    log_dir = "./log"
    if not os.path.exists(log_dir):
        os.mkdir(log_dir)
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(name)s %(levelname)s %(message)s',
                        datefmt='%m-%d %H:%M',
                        filename='{}/{}.log'.format(log_dir, config.model_prefix),
                        filemode='a')
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(name)s %(levelname)s %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

    # set up environment
    devs = [mx.gpu(int(i)) for i in config.gpu_list]
    kv = mx.kvstore.create(config.kv_store)

    # set up iterator and symbol
    # iterator
    train, val, num_examples = imagenet_iterator(data_dir=config.data_dir,
                                                 batch_size=config.batch_size,
                                                 kv=kv)
    print train
    print val
    data_names = ('data',)
    label_names = ('softmax_label',)
    data_shapes = [('data', (config.batch_size, 3, 224, 224))]
    label_shapes = [('softmax_label', (config.batch_size,))]

    if config.network == 'resnet' or config.network == 'resnext':
        symbol = eval(config.network)(units=config.units,
                                      num_stage=config.num_stage,
                                      filter_list=config.filter_list,
                                      num_classes=config.num_classes,
                                      data_type=config.dataset,
                                      bottle_neck=config.bottle_neck)
    elif config.network == 'vgg16' or config.network == 'mobilenet' or config.network == 'shufflenet':
        symbol = eval(config.network)(num_classes=config.num_classes)

    # train
    epoch_size = max(int(num_examples / config.batch_size / kv.num_workers), 1)
    if config.lr_step is not None:
        lr_scheduler = multi_factor_scheduler(config.begin_epoch, epoch_size, step=config.lr_step,
                                              factor=config.lr_factor)
    else:
        lr_scheduler = None

    optimizer_params = {'learning_rate': config.lr,
                        'lr_scheduler': lr_scheduler,
                        'wd': config.wd,
                        'momentum': config.momentum}
    optimizer = "nag"
    #optimizer = 'sgd'
    eval_metric = ['acc']
    if config.dataset == "imagenet":
        eval_metric.append(mx.metric.create('top_k_accuracy', top_k=5))

    solver = Solver(symbol=symbol,
                    data_names=data_names,
                    label_names=label_names,
                    data_shapes=data_shapes,
                    label_shapes=label_shapes,
                    logger=logging,
                    context=devs)
    epoch_end_callback = mx.callback.do_checkpoint("./model/" + config.model_prefix)
    batch_end_callback = mx.callback.Speedometer(config.batch_size, config.frequent)
    initializer = mx.init.Xavier(rnd_type='gaussian', factor_type='in', magnitude=2)
    arg_params = None
    aux_params = None
    if config.retrain:
        _, arg_params, aux_params = mx.model.load_checkpoint("model/{}".format(config.model_load_prefix),
                                                             config.model_load_epoch)
    solver.fit(train_data=train,
               eval_data=val,
               eval_metric=eval_metric,
               epoch_end_callback=epoch_end_callback,
               batch_end_callback=batch_end_callback,
               initializer=initializer,
               arg_params=arg_params,
               aux_params=aux_params,
               optimizer=optimizer,
               optimizer_params=optimizer_params,
               begin_epoch=config.begin_epoch,
               num_epoch=config.num_epoch,
               kvstore=kv)


if __name__ == '__main__':
    main(config)
