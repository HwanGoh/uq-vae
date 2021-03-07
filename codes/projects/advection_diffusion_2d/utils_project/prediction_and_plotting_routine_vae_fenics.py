#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
import os

sys.path.insert(0, os.path.realpath('../../../../../fenics-simulations/src'))

import numpy as np
import pandas as pd

# Import src code
from utils_data.data_handler import DataHandler
from neural_networks.nn_vae import VAE
from utils_misc.positivity_constraints import positivity_constraint_log_exp

# Import project utilities
from utils_project.plot_fem_function_fenics_2d import plot_fem_function_fenics_2d
from utils_project.plot_cross_section import plot_cross_section

# Import FEniCS code
from utils_mesh.construct_mesh_rectangular_with_hole import construct_mesh

import pdb #Equivalent of keyboard in MATLAB, just add "pdb.set_trace()"

###############################################################################
#                              Plot Predictions                               #
###############################################################################
def predict_and_plot(hyperp, options, filepaths):

    #=== Mesh Properties ===#
    options.hole_single_circle = False
    options.hole_two_rectangles = True
    options.discretization_domain = 17
    options.domain_length = 1
    options.domain_width = 1
    options.rect_1_point_1 = [0.25, 0.15]
    options.rect_1_point_2 = [0.5, 0.4]
    options.rect_2_point_1 = [0.6, 0.6]
    options.rect_2_point_2 = [0.75, 0.85]

    #=== Construct Mesh ===#
    Vh, nodes, dof = construct_mesh(options)

    #=== Load Observation Indices ===#
    obs_dimensions = options.num_obs_points*options.num_time_steps
    print('Loading Boundary Indices')
    df_obs_indices = pd.read_csv(filepaths.project.obs_indices + '.csv')
    obs_indices = df_obs_indices.to_numpy()

    #=== Data and Latent Dimensions of Autoencoder ===#
    input_dimensions = obs_dimensions
    latent_dimensions = options.parameter_dimensions

    #=== Prepare Data ===#
    data = DataHandler(hyperp, options, filepaths,
                       options.parameter_dimensions, obs_dimensions)
    # data.load_data_specific()
    # if options.add_noise == 1:
    #     data.add_noise_qoi_specific()
    # parameter_test = data.poi_specific
    # state_obs_test = data.qoi_specific

    data.load_data_test()
    if options.add_noise == True:
        data.add_noise_qoi_test()
    parameter_test = data.poi_test
    state_obs_test = data.qoi_test

    #=== Load Trained Neural Network ===#
    nn = VAE(hyperp, options,
             input_dimensions, latent_dimensions,
             None, None,
             positivity_constraint_log_exp)
    nn.load_weights(filepaths.trained_nn)

    #=== Selecting Samples ===#
    sample_number = 15
    parameter_test_sample = np.expand_dims(parameter_test[sample_number,:], 0)
    state_obs_test_sample = np.expand_dims(state_obs_test[sample_number,:], 0)

    #=== Predictions ===#
    posterior_mean_pred, posterior_cov_pred = nn.encoder(state_obs_test_sample)
    posterior_pred_draw = nn.reparameterize(posterior_mean_pred, posterior_cov_pred)

    posterior_mean_pred = posterior_mean_pred.numpy().flatten()
    posterior_cov_pred = posterior_cov_pred.numpy().flatten()
    posterior_pred_draw = posterior_pred_draw.numpy().flatten()

    if options.model_aware == 1:
        state_obs_pred_draw = nn.decoder(np.expand_dims(posterior_pred_draw, 0))
        state_obs_pred_draw = state_obs_pred_draw.numpy().flatten()

    #=== Plotting Prediction ===#
    print('================================')
    print('      Plotting Predictions      ')
    print('================================')

    #=== Plot FEM Functions ===#
    cross_section_y = 0.8
    filename_extension = '_%d.png'%(sample_number)
    plot_fem_function_fenics_2d(Vh, parameter_test_sample,
                                cross_section_y,
                                '',
                                filepaths.figure_parameter_test + filename_extension,
                                (5,5), (0,5),
                                False)
    plot_fem_function_fenics_2d(Vh, posterior_mean_pred,
                                cross_section_y,
                                '',
                                filepaths.figure_posterior_mean + filename_extension,
                                (5,5), (0,5),
                                True)
    plot_fem_function_fenics_2d(Vh, posterior_pred_draw,
                                cross_section_y,
                                '',
                                filepaths.figure_parameter_pred + filename_extension,
                                (5,5), (0,5),
                                True)
    if options.obs_type == 'full':
        plot_fem_function_fenics_2d(Vh, state_obs_test_sample,
                                    cross_section_y,
                                    'True State',
                                    filepaths.figure_state_test + filename_extension,
                                    (5,5))
        plot_fem_function_fenics_2d(Vh, state_obs_pred_draw,
                                    cross_section_y,
                                    'State Prediction',
                                    filepaths.figure_state_pred + filename_extension,
                                    (5,5))

    #=== Plot Cross-Section with Error Bounds ===#
    plot_cross_section(Vh,
                       parameter_test_sample, posterior_mean_pred, posterior_cov_pred,
                       (0,1), cross_section_y,
                       '',
                       filepaths.figure_parameter_cross_section + filename_extension,
                       (0,5))

    print('Predictions plotted')
