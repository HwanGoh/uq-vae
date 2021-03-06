import tensorflow as tf
import numpy as np
import pandas as pd
import time

import pdb #Equivalent of keyboard in MATLAB, just add "pdb.set_trace()"

###############################################################################
#                                   Neumann                                   #
###############################################################################
class SolveFEMPoissonHeatLinearAssembled:
    def __init__(self, options, filepaths,
                 obs_indices,
                 forward_matrix, mass_matrix,
                 load_vector):

        #=== Defining Attributes ===#
        self.options = options
        self.filepaths = filepaths
        self.obs_indices = tf.cast(obs_indices, tf.int32)
        self.forward_matrix = forward_matrix
        self.mass_matrix = mass_matrix
        self.load_vector = load_vector

    def solve_pde(self, parameters):
        #=== Solving PDE ===#
        rhs = tf.linalg.matmul(
                tf.expand_dims(parameters[0,:], axis=0), tf.transpose(self.mass_matrix))\
                + tf.transpose(self.load_vector)
        state = tf.linalg.matmul(rhs, tf.transpose(self.forward_matrix))
        for n in range(1, parameters.shape[0]):
            rhs = tf.linalg.matmul(
                    tf.expand_dims(parameters[n,:], axis=0), tf.transpose(self.mass_matrix))\
                    + tf.transpose(self.load_vector)
            solution = tf.linalg.matmul(rhs, tf.transpose(self.forward_matrix))
            state = tf.concat([state, solution], axis=0)

        #=== Generate Measurement Data ===#
        if self.options.obs_type == 'obs':
            state_obs = tf.gather(state, self.obs_indices, axis=1)
            return tf.squeeze(state_obs)
        else:
            return state
