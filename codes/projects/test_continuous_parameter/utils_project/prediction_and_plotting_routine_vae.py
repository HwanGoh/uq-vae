'''Prediction and plotting routine

In preparation for prediction and plotting, this script will:
    1) Load the obs_dimensions
    2) Specify the input_dimensions and latent_dimensions
    3) Instantiate the DataHandler class
    4) Instantiate the neural network
    5) Load the trained neural network weights
    6) Select and prepare an illustrative test example
    7) Output a prediction of the posterior mean and posterior covariance by
       utilizing the encoder
    8) Draw from the predicted posterior
    9) Predict the state using the draw from the posterior either using the
       modelled or learned (decoder) parameter-to-observable map
    10) Plot the prediction

Inputs:
    - hyperp: dictionary storing set hyperparameter values
    - options: dictionary storing the set options
    - filepaths: instance of the FilePaths class storing the default strings for
                 importing and exporting required objects.

Author: Hwan Goh, Oden Institute, Austin, Texas 2020
'''
import sys

import tensorflow as tf
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
plt.ioff() # Turn interactive plotting off
import scipy.stats as st

# Import src code
from utils_data.data_handler import DataHandler
from neural_networks.nn_vae_full import VAE
from utils_misc.positivity_constraints import positivity_constraint_log_exp

# Import project utilities
from utils_project.get_forward_operators_tf import load_forward_operator_tf
from utils_project.solve_forward_1d import SolveForward1D

import pdb #Equivalent of keyboard in MATLAB, just add "pdb.set_trace()"

###############################################################################
#                              Plot Predictions                               #
###############################################################################
def predict_and_plot(hyperp, options, filepaths):

    #=== Load Observation Indices ===#
    if options.obs_type == 'full':
        obs_dimensions = options.mesh_dimensions
        obs_indices = []
    if options.obs_type == 'obs':
        obs_dimensions = options.num_obs_points
        print('Loading Boundary Indices')
        df_obs_indices = pd.read_csv(filepaths.project.obs_indices + '.csv')
        obs_indices = df_obs_indices.to_numpy()

    #=== Data and Latent Dimensions of Autoencoder ===#
    input_dimensions = obs_dimensions
    latent_dimensions = options.parameter_dimensions

    #=== Prepare Data ===#
    data = DataHandler(hyperp, options, filepaths,
                       obs_indices,
                       options.parameter_dimensions, obs_dimensions,
                       options.mesh_dimensions)
    data.load_data_test()
    if options.add_noise == 1:
        data.add_noise_qoi_test()
    parameter_test = data.poi_test
    state_obs_test = data.qoi_test

    #=== Load Trained Neural Network ===#
    nn = VAE(hyperp, options,
             input_dimensions, latent_dimensions,
             None, None,
             tf.identity)
    nn.load_weights(filepaths.trained_nn)

    #=== Construct Forward Model ===#
    if options.model_augmented == True:
        forward_operator = load_forward_operator_tf(options, filepaths)
        forward_model =\
                SolveForward1D(options, filepaths, forward_operator, obs_indices)
        if options.discrete_polynomial == True:
            forward_model_solve = forward_model.discrete_polynomial
        if options.discrete_exponential == True:
            forward_model_solve = forward_model.discrete_exponential

    #=== Selecting Samples ===#
    sample_number = 105
    parameter_test_sample = np.expand_dims(parameter_test[sample_number,:], 0)
    state_obs_test_sample = np.expand_dims(state_obs_test[sample_number,:], 0)

    #=== Predictions ===#
    post_mean_pred, log_post_std_pred, post_cov_chol_pred = nn.encoder(state_obs_test_sample)
    n_samples = 1000
    posterior_pred_draws = np.zeros((n_samples, post_mean_pred.shape[1]),
                                dtype=np.float32)
    state_obs_pred_draws = np.zeros((n_samples, state_obs_test_sample.shape[1]),
                                dtype=np.float32)
    for n in range(0,n_samples):
        posterior_pred_draws[n,:] = nn.reparameterize(post_mean_pred, post_cov_chol_pred)
    if options.model_aware == True:
        state_obs_pred_draws = nn.decoder(posterior_pred_draws)
    else:
        state_obs_pred_draws = forward_model_solve(posterior_pred_draws)

    #=== Plotting Prediction ===#
    print('================================')
    print('      Plotting Predictions      ')
    print('================================')
    n_bins = 100
    for n in range(0, post_mean_pred.shape[1]):
        #=== Posterior Histogram ===#
        plt.hist(posterior_pred_draws[:,n], density=True,
                 range=[-1,10], bins=n_bins)
        #=== True Parameter Value ===#
        plt.axvline(parameter_test_sample[0,n], color='r',
                linestyle='dashed', linewidth=3,
                label="True Parameter Value")
        #=== Predicted Posterior Mean ===#
        plt.axvline(post_mean_pred[0,n], color='b',
                linestyle='dashed', linewidth=1,
                label="Predicted Posterior Mean")
        #=== Probability Density Function ===#
        mn, mx = plt.xlim()
        plt.xlim(mn, mx)
        kde_xs = np.linspace(mn, mx, 301)
        kde = st.gaussian_kde(posterior_pred_draws[:,n])
        #=== Title and Labels ===#
        plt.plot(kde_xs, kde.pdf(kde_xs))
        plt.legend(loc="upper left")
        plt.ylabel('Probability')
        plt.xlabel('Parameter Value')
        plt.title("Marginal Posterior Parameter_%d"%(n));
        #=== Save and Close Figure ===#
        plt.savefig(filepaths.figure_parameter_pred + '_%d'%(n))
        plt.close()

    print('Predictions plotted')
