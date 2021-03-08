'''Optimization routine for the case where the model
posterior possesses a full covariance and the parameter-to-observable map is
modelled and linear.

In preparation for optimization, this script will:
    1) Constuct any objects necessary to be passed to the loss functionals
    2) Instantiate the Metrics class
    3) Instantiate the Tensorboard summary_writer
    4) Build the neural network and display a summary

Then, per epoch, this script will:
    1) Using train_step() form the batched gradient using the training set
    2) Using val_step() evaluate the metrics on the validation set
    3) Using test_step() evaluate the metrics on the testing set
    4) Update the Tensorboard metrics
    5) Update the storage arrays
    6) Display and reset the current metric values
    7) Output the metrics, current values of the neural network weights and
       dump the hyperp and options dictionaries into uq-vae/trained_nns/

Inputs:
    - hyperp: dictionary storing set hyperparameter values
    - options: dictionary storing the set options
    - filepaths: instance of the FilePaths class storing the default strings for
                 importing and exporting required objects.
    - nn: the neural network to be trained
    - optimizer: Tensorflow optimizer to be used
    - input_and_latent_: batched train, validation and testing datasets
    - input_dimension: dimension of the input layer of the neural network
    - latent_dimension: dimension of the model posterior mean estimate output by
                        the encoder
    - num_batches_train: batch_size
    - noise_regularization_matrix: noise covariance matrix for the likelihood term
    - measurement_matrix: operator that extracts the values at the measurement points
                          to be used in the trace term of the likelihood term
                          which appears in the case of a linear
                          parameter-to-observable map
    - prior_mean: mean of the prior model
    - prior_cov_inv: inverse of the covariance of the prior model
    - forward_matrix: the matrix representing the model of the linear
                      parameter-to-observable map
    - solve_forward_model: operation of the parameter-to-observable map

Author: Hwan Goh, Oden Institute, Austin, Texas 2020
'''
import sys
sys.path.append('../..')

import shutil # for deleting directories
import os
import time

import tensorflow as tf
import numpy as np
import pandas as pd

# Import src code
from utils_training.metrics_vae import Metrics
from utils_io.config_io import dump_attrdict_as_yaml
from utils_training.functionals import\
        loss_weighted_penalized_difference,\
        loss_weighted_post_cov_full_penalized_difference,\
        loss_trace_likelihood,\
        loss_kld_full,\
        relative_error

import pdb #Equivalent of keyboard in MATLAB, just add "pdb.set_trace()"

###############################################################################
#                             Training Properties                             #
###############################################################################
def optimize(hyperp, options, filepaths,
             nn, optimizer,
             input_and_latent_train, input_and_latent_val, input_and_latent_test,
             input_dimensions, latent_dimension, num_batches_train,
             noise_regularization_matrix, measurement_matrix,
             prior_mean, prior_cov_inv,
             forward_matrix, solve_forward_model):

    #=== Kronecker Product of Identity and Prior Covariance Inverse ===#
    identity_otimes_prior_cov_inv =\
            tf.linalg.LinearOperatorKronecker(
                    [tf.linalg.LinearOperatorFullMatrix(tf.eye(latent_dimension)),
                    tf.linalg.LinearOperatorFullMatrix(prior_cov_inv)])

    #=== Kronecker Product of Identity and Likelihood Matrix ===#
    if measurement_matrix.shape == (1,1):
        likelihood_matrix = tf.linalg.matmul(tf.transpose(forward_matrix),
                                    noise_regularization_matrix*forward_matrix)
    else:
        likelihood_matrix = tf.linalg.matmul(
                                tf.transpose(tf.linalg.matmul(measurement_matrix,forward_matrix)),
                                tf.linalg.matmul(
                                    tf.linalg.diag(tf.squeeze(noise_regularization_matrix)),
                                    tf.linalg.matmul(measurement_matrix,forward_matrix)))
    identity_otimes_likelihood_matrix =\
            tf.linalg.LinearOperatorKronecker(
                    [tf.linalg.LinearOperatorFullMatrix(tf.eye(latent_dimension)),
                    tf.linalg.LinearOperatorFullMatrix(likelihood_matrix)])

    #=== Define Metrics ===#
    metrics = Metrics()

    #=== Creating Directory for Trained Neural Network ===#
    if not os.path.exists(filepaths.directory_trained_nn):
        os.makedirs(filepaths.directory_trained_nn)

    #=== Tensorboard ===# "tensorboard --logdir=tensorboard"
    if os.path.exists(filepaths.directory_tensorboard):
        shutil.rmtree(filepaths.directory_tensorboard)
    summary_writer = tf.summary.create_file_writer(filepaths.directory_tensorboard)

    #=== Display Neural Network Architecture ===#
    nn.build((hyperp.batch_size, input_dimensions))
    nn.summary()

###############################################################################
#                   Training, Validation and Testing Step                     #
###############################################################################
    #=== Train Step ===#
    @tf.function
    def train_step(batch_input_train, batch_latent_train):
        with tf.GradientTape() as tape:
            batch_post_mean_train, batch_log_post_std_train, batch_post_cov_chol_train\
                    = nn.encoder(batch_input_train)
            batch_input_pred_forward_model_train =\
                    solve_forward_model(batch_post_mean_train)

            batch_loss_train_vae =\
                    loss_trace_likelihood(batch_post_cov_chol_train,
                            identity_otimes_likelihood_matrix,
                            1) +\
                    loss_weighted_penalized_difference(
                            batch_input_train, batch_input_pred_forward_model_train,
                            noise_regularization_matrix,
                            1)
            batch_loss_train_kld =\
                    loss_kld_full(
                            batch_post_mean_train, batch_log_post_std_train,
                            batch_post_cov_chol_train,
                            prior_mean, prior_cov_inv, identity_otimes_prior_cov_inv,
                            1)
            batch_loss_train_posterior =\
                    (1-hyperp.penalty_js)/hyperp.penalty_js *\
                    2*tf.reduce_sum(batch_log_post_std_train,axis=1) +\
                    loss_weighted_post_cov_full_penalized_difference(
                            batch_latent_train, batch_post_mean_train,
                            batch_post_cov_chol_train,
                            (1-hyperp.penalty_js)/hyperp.penalty_js)

            batch_loss_train = -(-batch_loss_train_vae\
                                 -batch_loss_train_kld\
                                 -batch_loss_train_posterior)

        gradients = tape.gradient(batch_loss_train, nn.trainable_variables)
        optimizer.apply_gradients(zip(gradients, nn.trainable_variables))
        metrics.mean_loss_train(batch_loss_train)
        metrics.mean_loss_train_vae(batch_loss_train_vae)
        metrics.mean_loss_train_encoder(batch_loss_train_kld)
        metrics.mean_loss_train_posterior(batch_loss_train_posterior)

        return gradients

    #=== Validation Step ===#
    @tf.function
    def val_step(batch_input_val, batch_latent_val):
        batch_post_mean_val, batch_log_post_std_val, batch_post_cov_chol_val\
                = nn.encoder(batch_input_val)

        batch_loss_val_kld =\
                loss_kld_full(
                        batch_post_mean_val, batch_log_post_std_val,
                        batch_post_cov_chol_val,
                        prior_mean, prior_cov_inv, identity_otimes_prior_cov_inv,
                        1)
        batch_loss_val_posterior =\
                (1-hyperp.penalty_js)/hyperp.penalty_js *\
                2*tf.reduce_sum(batch_log_post_std_val,axis=1) +\
                loss_weighted_post_cov_full_penalized_difference(
                        batch_latent_val, batch_post_mean_val,
                        batch_post_cov_chol_val,
                        (1-hyperp.penalty_js)/hyperp.penalty_js)

        batch_loss_val = -(-batch_loss_val_kld\
                           -batch_loss_val_posterior)

        metrics.mean_loss_val(batch_loss_val)
        metrics.mean_loss_val_encoder(batch_loss_val_kld)
        metrics.mean_loss_val_posterior(batch_loss_val_posterior)

    #=== Test Step ===#
    @tf.function
    def test_step(batch_input_test, batch_latent_test):
        batch_post_mean_test, batch_log_post_std_test, batch_post_cov_chol_test\
                = nn.encoder(batch_input_test)

        batch_loss_test_kld =\
                loss_kld_full(
                        batch_post_mean_test, batch_log_post_std_test,
                        batch_post_cov_chol_test,
                        prior_mean, prior_cov_inv, identity_otimes_prior_cov_inv,
                        1)
        batch_loss_test_posterior =\
                (1-hyperp.penalty_js)/hyperp.penalty_js *\
                2*tf.reduce_sum(batch_log_post_std_test,axis=1) +\
                loss_weighted_post_cov_full_penalized_difference(
                        batch_latent_test, batch_post_mean_test,
                        batch_post_cov_chol_test,
                        (1-hyperp.penalty_js)/hyperp.penalty_js)

        batch_loss_test = -(-batch_loss_test_kld\
                            -batch_loss_test_posterior)

        metrics.mean_loss_test(batch_loss_test)
        metrics.mean_loss_test_encoder(batch_loss_test_kld)
        metrics.mean_loss_test_posterior(batch_loss_test_posterior)

        metrics.mean_relative_error_latent_posterior(relative_error(
            batch_latent_test, batch_post_mean_test))

###############################################################################
#                             Train Neural Network                            #
###############################################################################
    print('Beginning Training')
    for epoch in range(hyperp.num_epochs):
        print('================================')
        print('            Epoch %d            ' %(epoch))
        print('================================')
        print('Project: ' + filepaths.case_name + '\n' + 'nn: ' + filepaths.nn_name + '\n')
        print('GPU: ' + options.which_gpu + '\n')
        print('Optimizing %d batches of size %d:' %(num_batches_train, hyperp.batch_size))
        start_time_epoch = time.time()
        for batch_num, (batch_input_train, batch_latent_train) in input_and_latent_train.enumerate():
            start_time_batch = time.time()
            #=== Computing Train Step ===#
            gradients = train_step(batch_input_train, batch_latent_train)
            elapsed_time_batch = time.time() - start_time_batch
            if batch_num  == 0:
                print('Time per Batch: %.4f' %(elapsed_time_batch))

        #=== Computing Relative Errors Validation ===#
        for batch_input_val, batch_latent_val in input_and_latent_val:
            val_step(batch_input_val, batch_latent_val)

        #=== Computing Relative Errors Test ===#
        for batch_input_test, batch_latent_test in input_and_latent_test:
            test_step(batch_input_test, batch_latent_test)

        #=== Update Current Relative Gradient Norm ===#
        with summary_writer.as_default():
            for w in nn.weights:
                tf.summary.histogram(w.name, w, step=epoch)
            l2_norm = lambda t: tf.sqrt(tf.reduce_sum(tf.pow(t, 2)))
            sum_gradient_norms = 0.0
            for gradient, variable in zip(gradients, nn.trainable_variables):
                tf.summary.histogram("gradients_norm/" + variable.name, l2_norm(gradient),
                        step = epoch)
                sum_gradient_norms += l2_norm(gradient)
                if epoch == 0:
                    initial_sum_gradient_norms = sum_gradient_norms
        metrics.relative_gradient_norm = sum_gradient_norms/initial_sum_gradient_norms

        #=== Track Training Metrics, Weights and Gradients ===#
        metrics.update_tensorboard(summary_writer, epoch)

        #=== Update Storage Arrays ===#
        metrics.update_storage_arrays()

        #=== Display Epoch Iteration Information ===#
        elapsed_time_epoch = time.time() - start_time_epoch
        print('Time per Epoch: %.4f\n' %(elapsed_time_epoch))
        print('Train Loss: Full: %.3e, VAE: %.3e, KLD: %.3e, Posterior: %.3e'\
                %(metrics.mean_loss_train.result(),
                  metrics.mean_loss_train_vae.result(),
                  metrics.mean_loss_train_encoder.result(),
                  metrics.mean_loss_train_posterior.result()))
        print('Val Loss: Full: %.3e, KLD: %.3e, Posterior: %.3e'\
                %(metrics.mean_loss_val.result(),
                  metrics.mean_loss_val_encoder.result(),
                  metrics.mean_loss_val_posterior.result()))
        print('Test Loss: Full: %.3e, KLD: %.3e, Posterior: %.3e'\
                %(metrics.mean_loss_test.result(),
                  metrics.mean_loss_test_encoder.result(),
                  metrics.mean_loss_test_posterior.result()))
        print('Rel Errors: Posterior Mean : %.3e\n'\
                %(metrics.mean_relative_error_latent_posterior.result()))
        print('Relative Gradient Norm: %.4f\n' %(metrics.relative_gradient_norm))
        start_time_epoch = time.time()

        #=== Resetting Metrics ===#
        metrics.reset_metrics()

        #=== Saving Current Model and  Metrics ===#
        if epoch %100 ==0:
            nn.save_weights(filepaths.trained_nn)
            metrics.save_metrics(filepaths)
            dump_attrdict_as_yaml(hyperp, filepaths.directory_trained_nn, 'hyperp')
            dump_attrdict_as_yaml(options, filepaths.directory_trained_nn, 'options')
            print('Current Model and Metrics Saved')

        #=== Gradient Norm Termination Condition ===#
        if metrics.relative_gradient_norm < 1e-6:
            print('Gradient norm tolerance reached, breaking training loop')
            break

    #=== Save Final Model ===#
    nn.save_weights(filepaths.trained_nn)
    metrics.save_metrics(filepaths)
    dump_attrdict_as_yaml(hyperp, filepaths.directory_trained_nn, 'hyperp')
    dump_attrdict_as_yaml(options, filepaths.directory_trained_nn, 'options')
    print('Final Model and Metrics Saved')