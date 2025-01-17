# -*- coding: utf-8 -*-
"""
Driver model for Landlab Model 000 Basic

Katy Barnhart March 2017
"""
import subprocess
import os
import sys
import time

eval_log = open('evaluation_log.txt', 'w')

current_directory = os.getcwd()
eval_log.write(current_directory+'\n')

# determine wall time
output,error = subprocess.Popen(['squeue',
                                      '--job='+os.environ['SLURM_JOB_ID'], '--format=%.10L'],
                                     stdout = subprocess.PIPE,
                                     stderr = subprocess.PIPE).communicate()
time_left = output.strip().split(' ')[-1]
try:
    hours_left = int(time_left.split(':')[-3])
except IndexError:
    hours_left = 0

eval_log.write('Wall time has '+str(hours_left)+' hours remaining.\n')

# handle the possiblity of not finishing in 24 hours, or an instability:
# first, set the default of running the model to True
run_model = True
if  os.path.exists('fail_log.txt'):
    eval_log.write('A fail_log.txt file exists\n')
    with open('fail_log.txt', 'r') as fp:
        lines = fp.readlines()
    for line in lines:
        if 'fail' in line:
            run_model = False
            fail = True
            eval_log.write('The fail_log.txt file indicates failure\n')
else:
    # if 'outputs_for_analysis.txt' already exists, and no failure log exists,
    # then copy it to results.out
    # adding this because I found it in sew 010 run 26
    if os.path.exists('outputs_for_analysis.txt'):
        with open('outputs_for_analysis.txt', 'r') as f:
            lines = f.readlines()
            if len(lines) == 20:
                run_model = False
                fail = False
                eval_log.write('outputs_for_analysis exists, copying it to results.out\n')
    else:
        # if no output exists and sufficient wall time remains,
        #  write out "fail"
        # this means that if things fail in the future,
        if hours_left >= 23:
            eval_log.write('Sufficient time exists, writing a new fail_log.txt file to be removed in case of sucess\n')
            with open('fail_log.txt', 'w') as fp:
                fp.write('fail')

            # write to results.out this will be overwritten in case of sucess.
            with open(sys.argv[3], 'w') as fp:
                fp.write('fail\n')

eval_log.close()

import shutil

if run_model:
    # import resource calculation modules and start logging usage
    import resource

    # import remaining required modules.

    from subprocess import call
    from yaml import load
    import numpy as np

    import os
    import dill as pickle

    from erosion_model import Basic as Model
    from metric_calculator import GroupedDifferences
    from landlab import imshow_grid

    # set files and directories used to set input templates.
    # Files and directories.
    start_dir = sys.argv[1]
    input_file = 'inputs.txt'
    input_template = 'inputs_template.txt'

    # Use `dprepro` (from $DAKOTA_DIR/bin) to substitute parameter
    # values from Dakota into the SWASH input template, creating a new
    # inputs.txt file.
    shutil.copy(os.path.join(start_dir, input_template), os.curdir)
    call(['dprepro', sys.argv[2], input_template, input_file])
    call(['rm', input_template])

    start_time = time.time()
    with open('usage.txt', 'a') as usage_file:
        usage_file.write(time.ctime()+'\n')

    # now prepare to run landlab.
    # load the params file to get the correct file names
    with open(input_file, 'r+') as f:
        # load params file
        params = load(f)

    # get filenames/etc.
    modern_dem_name = params['modern_dem_name']
    outlet_id = params['outlet_id']
    #modern_dem_metric_file = params['modern_dem_metric_file']
    #modern_dem_chi_file = params['modern_dem_chi_file']
    #chi_mask_dem_name = params['chi_mask_dem_name']
    outlet_id = params['outlet_id']
    category_file = params['category_file']
    category_values = np.loadtxt(category_file)
    category_weight_file = params['category_weight_file']
    weight_values = np.loadtxt(category_weight_file)

    #plan for output files
    output_fields =['topographic__elevation']

    # write usage
    with open('usage.txt', 'a') as usage_file:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        usage_file.write('\n\nUsage Before Running Model: \n')
        for name, desc in [
            ('ru_utime', 'User time'),
            ('ru_stime', 'System time'),
            ('ru_maxrss', 'Max. Resident Set Size'),
            ('ru_ixrss', 'Shared Memory Size'),
            ('ru_idrss', 'Unshared Memory Size'),
            ('ru_isrss', 'Stack Size'),
            ('ru_inblock', 'Block inputs'),
            ('ru_oublock', 'Block outputs'),
            ]:
            usage_file.write('%-25s (%-10s) = %s \n'%(desc, name, getattr(usage, name)))

    #run the model
    # if a restart file exists, start from there, otherwise,
    # initialize from the input file.
    saved_model_object = 'saved_model.model'
    if os.path.exists(saved_model_object):
        try:
            with open(saved_model_object, 'rb') as f:
                model = pickle.load(f)
        except:
            model = Model(input_file)
    else:
        model = Model(input_file)

    model.run(output_fields=output_fields)

    with open('usage.txt', 'a') as usage_file:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        usage_file.write('\n\nUsage After Running Model: \n')
        for name, desc in [
            ('ru_utime', 'User time'),
            ('ru_stime', 'System time'),
            ('ru_maxrss', 'Max. Resident Set Size'),
            ('ru_ixrss', 'Shared Memory Size'),
            ('ru_idrss', 'Unshared Memory Size'),
            ('ru_isrss', 'Stack Size'),
            ('ru_inblock', 'Block inputs'),
            ('ru_oublock', 'Block outputs'),
            ]:
            usage_file.write('%-25s (%-10s) = %s \n'%(desc, name, getattr(usage, name)))

    model_dem_name = model.params['output_filename'] + \
        str(model.iteration-1).zfill(4) + \
            '.nc'

    # calculate metrics
    gd = GroupedDifferences(model_dem_name, modern_dem_name,
                            outlet_id=outlet_id,
                            category_values=category_values,
                            weight_values=weight_values)
    gd.calculate_metrics()

    # write out metrics as "ouputs_for_analysis.txt' and as Dakota expects.
    output_bundle = gd.dakota_bundle()
    with open('outputs_for_analysis.txt', 'w') as fp:
        for metric in output_bundle:
            fp.write(str(metric)+'\n')

        # if a fail log was written (23 hours was on clock at start of
        # attempt) then remove it.
        if os.path.exists('fail_log.txt'):
            call(['rm', 'fail_log.txt'])
        # write out residual. This will replace the fail used before.
        with open(sys.argv[3], 'w') as fp:
            for metric in output_bundle:
                fp.write(str(metric)+'\n')

    cur_working = os.getcwd()
    cur_working_split = cur_working.split(os.path.sep)
    cur_working_split.append('png')
    try:
        cut_ind = cur_working_split.index('results')+3
    except:
        cut_ind = cur_working_split.index('study3py')+3

    fig_name = '.'.join(cur_working_split[cut_ind:])

    imshow_grid(model.grid, model.z, vmin=1230, vmax=1940, cmap='viridis', output=fig_name)

    with open('usage.txt', 'a') as usage_file:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        usage_file.write('\n\nUsage At End of Job: \n')
        for name, desc in [
            ('ru_utime', 'User time'),
            ('ru_stime', 'System time'),
            ('ru_maxrss', 'Max. Resident Set Size'),
            ('ru_ixrss', 'Shared Memory Size'),
            ('ru_idrss', 'Unshared Memory Size'),
            ('ru_isrss', 'Stack Size'),
            ('ru_inblock', 'Block inputs'),
            ('ru_oublock', 'Block outputs'),
            ]:
            usage_file.write('%-25s (%-10s) = %s \n'%(desc, name, getattr(usage, name)))

        end_time = time.time()
        usage_file.write('\n\n'+time.ctime()+'\n')
        usage_file.write('Elapsed Time: '+str(end_time-start_time)+'\n')
else:
    if fail:
        # model isn't run b/c of failure of past attempt
        with open(sys.argv[3], 'w') as fp:
            fp.write('fail\n')
    else:
        # if outputs for analysis already existed and had 20 lines.
        shutil.copy('outputs_for_analysis.txt', sys.argv[3])
