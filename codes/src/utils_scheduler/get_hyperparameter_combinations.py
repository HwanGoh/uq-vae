###############################################################################
#                        Generate List of Scenarios                           #
###############################################################################
def get_hyperparameter_combinations(hyperp):
    '''Converts a dictionary containing lists of possible hyperparameter values
    to a list of dictionaries containing all combinations of these
    hyperparameter values.

    Ex. hyperp = {'a': [1, 2],
                    'b': ['c', 'd']}
        => scenarios = [{'a': 1, 'b': 'c'},
                        {'a': 1, 'b': 'd'},
                        {'a': 2, 'b': 'c'},
                        {'a': 2, 'b': 'd'}]

    Inputs:
        - hyperp: either dictionary or class whose attributes are hyperparameters

    Outputs:
        - scenarios: list of hyperparameter dictionaries.
                     each element of the list is one hyperparameter scenario

    Author: Jonathan Wittmer, Oden Institute, Austin, Texas 2020
    '''
    hyperp_dict = hyperp.__dict__ if not isinstance(hyperp, dict) else hyperp
    hyperp_keys = list(hyperp_dict.keys())
    hyperp_vals = list(hyperp_dict.values())
    combinations_list = generate_combinations(hyperp_vals[0], hyperp_vals[1:])
    scenarios = assemble_scenarios_dictionaries(combinations_list, hyperp_keys)

    return scenarios

def generate_combinations(curr_hyperp, hyperp_vals):
    '''Recursive algorithm to generate a list of lists
    containing all the combinations of given set of
    inputs.

    Inputs:
        curr_hyperp : loop through the values of this hyperparameter
                      appending all the combinations of each subsequent
                      hyperparameter.
        hyperp_vals : list of the remaining hyperparameters. As the algorithm
                      runs, this list gets shorter until there is only
                      a single hyperparameter list

    Author: Jonathan Wittmer, Oden Institute, Austin, Texas 2020
    '''
    # reassign when it is not the last item - recursive algorithm
    if len(hyperp_vals) > 1:
        combos = generate_combinations(hyperp_vals[0], hyperp_vals[1:])
        is_last_value = False
    else:
        combos = hyperp_vals[0]
        is_last_value = True

    # concatenate the output into a list of lists
    output = []
    for i in curr_hyperp:
        for j in combos:
            # convert to list if not already for use with extend
            temp = [i]
            # if we want to keep the last item a list, use append, not extend
            if is_last_value and isinstance(j, list):
                temp.append(j)
            else:
                j = j if isinstance(j, list) else [j]
                temp.extend(j)
            output.append(temp)
    return output

def assemble_scenarios_dictionaries(combinations_list, hyperp_keys):
    '''Converts list of lists to list of dictionaries

    Inputs:
        - combinations_list: list of lists. the hyperparameter values.
        - hyperp_key: list of keys. the hyperparameter names

    Outputs:
        - scenarios: list of dictionaries

    Author: Jonathan Wittmer, Oden Institute, Austin, Texas 2020
    '''
    scenarios = []
    for scenario_list in combinations_list:
        curr_scenario = {}
        for key, value in zip(hyperp_keys, scenario_list):
            curr_scenario[key] = value
        scenarios.append(curr_scenario)
    return scenarios
