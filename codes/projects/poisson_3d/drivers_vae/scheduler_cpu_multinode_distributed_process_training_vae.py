#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''Schedules hyperparameter scenarios and drives training

You will need to specify:
    - In generate_scenarios_list() the set of hyperparameter scenarios you
      wish to use
    - In subprocess.Popen() whether the parameter-to-observable map is
      modelled or learned through specification of which training
      driver to call

Author: Jonathan Wittmer, Oden Institute, Austin, Texas 2019
'''
import socket
import subprocess
from mpi4py import MPI

import os
import sys
sys.path.insert(0, os.path.realpath('../../../src'))
import json

from utils_scheduler.get_hyperparameter_combinations import get_hyperparameter_combinations
from utils_scheduler.schedule_and_run_static import schedule_runs

import pdb #Equivalent of keyboard in MATLAB, just add "pdb.set_trace()"

class FLAGS:
    RECEIVED = 1
    RUN_FINISHED = 2
    EXIT = 3
    NEW_RUN = 4

###############################################################################
#                           Generate Scenarios List                           #
###############################################################################
def generate_scenarios_list():
    hyperp = {}
    hyperp['num_hidden_layers_encoder'] = [5]
    hyperp['num_hidden_layers_decoder'] = [2]
    hyperp['num_hidden_nodes_encoder']  = [500]
    hyperp['num_hidden_nodes_decoder']  = [500]
    hyperp['activation']                = ['relu']
    hyperp['penalty_js']                = [0.00001, 0.0001, 0.001, 0.01, 0.1]
    hyperp['num_data_train']            = [500, 1000, 2500, 5000]
    hyperp['batch_size']                = [100]
    hyperp['num_epochs']                = [1000]

    return get_hyperparameter_combinations(hyperp)

###############################################################################
#                                   Executor                                  #
###############################################################################
if __name__ == '__main__':

    '''
    description:
        Distributes the scenarios list with each scenario assigned to an
        individual CPU
    '''
    # mpi stuff
    comm   = MPI.COMM_WORLD
    nprocs = comm.Get_size()
    rank   = comm.Get_rank()

    # By running "mpirun -n <number> ./scheduler.py", each process is cycled through by their rank
    if rank == 0: # This is the master processes' action
        flags = FLAGS()
        # get scenarios list
        scenarios_list = generate_scenarios_list()

        # get the info for all processes
        processes = []
        while len(processes) < nprocs - 1:
            status = MPI.Status()
            comm.Iprobe(status=status)
            if status.tag == 1:
                print(f'status:{status.source}', flush=True)
                proc_info = comm.recv(source=status.source, tag=status.tag)
                processes.append(proc_info)
        print(processes)

        # static gpu assignment per process. Currently only a single gpu per process
        nodes = {}
        active_procs = []
        proc_to_cpu_mapping = {}

        for proc_info in processes:
            # keep track of the processes already found each node
            if proc_info['hostname'] not in nodes:
                nodes[proc_info['hostname']] = []
            nodes[proc_info['hostname']].append(str(proc_info['rank']))

            # only use the process if there are available gpus
            if len(nodes[proc_info['hostname']]) <= 1:
                active_procs.append(proc_info['rank'])
                proc_to_cpu_mapping[str(proc_info['rank'])] = 'cpu'
            else: # terminating the inactive redundant processes
                req = comm.isend([],proc_info['rank'],flags.EXIT )
                req.wait()

        for key, val in proc_to_cpu_mapping.items():
            print(f'process {key} running on cpu')

        # Schedule and run processes
        schedule_runs(scenarios_list, active_procs, proc_to_cpu_mapping, comm)

    else:
        # This is the worker processes' action
        # First send process info to master process
        # number of gpus in this node
        hostname = socket.gethostname()
        proc_info = {'rank': rank,
                     'hostname': hostname}
        req = comm.isend(proc_info, 0, 1)
        req.wait()

        while True:
            status = MPI.Status()
            scenario = comm.recv(source=0, status=status)

            if status.tag == FLAGS.EXIT:
                break

            # convert dictionary to json
            scenario_json = json.dumps(scenario)
            # proc = subprocess.Popen(['./training_vae_model_aware.py',
            #     f'{scenario_json}',f'{"cpu"}'])
            proc = subprocess.Popen(['./training_vae_model_augmented_autodiff.py',
                f'{scenario_json}',f'{"cpu"}'])
            proc.wait()

            req = comm.isend([], 0, FLAGS.RUN_FINISHED)
            req.wait()

    print('All scenarios computed')
