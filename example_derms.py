import time
import signal
import sys
import csv
import asyncio
import pandas as pd
import numpy as np
import datetime
from lab_demo_controller import ChargingManagementSystem
from derms_lib.derms_comms import DERMSComms


### Inputs ###
# replace the username and password with the username and password for your SCM on the DERMS
username = "my_username" 
password = "my_password"
derms_api_ip = 'http://127.0.0.1/json/reply/ReadApplicationPointWebRequest'
# this should be a list of names of EVSE that you have on your controlled site
# it is assumed that each EVSE has between 1 and 4 connectors. The number of connectors is determined by the derms_comms
plug_list = ['EVSE1', 'EVSE2']
# list names of any stationary storage 
ess_list = [] 
# list the names of any site utility meters as they appear on your DERMS
utility_meter_list = ['METER1']
# adjust the timestep size of your controller in seconds such that it is longer than the time it takes for your DERMS to update the EVSE power
step_size_sec = 35
# total capacity in kW should be adjusted to fit site constraints: likely either service panel or service transformer limit
total_capacity = 8
# update the SCM method to match desired control style
scm_method = 'equal_sharing'# other options include 'soc_priority','first_come_first_served', and 'priority_factor'
### End of Inputs ###

#Initialize evse_powerlimits as an empty dataframe
evse_powerlimits = pd.DataFrame()       

#Creates a function that clears power limits when script is killed with CTRL + c
def clean_exit_handler(sig, frame):
    if not evse_powerlimits.columns.empty:      #If evse_powerlimits has values
        for evse in evse_powerlimits.columns:      #iterate over the EVSEs and clears the power limit for each connector
            for connector in range(4):
                derms.clear_evse_power_limit(evse, connector=connector)
                print(f"Cleared power limit for EVSE: {evse} connector: {connector}")
        print("Exiting script.")    
    else:
        print("No power limits have been assigned yet. Exiting script.")
    sys.exit(0)

#Attach clean exit handler to SIGINT (when user hits CTRL + C)
signal.signal(signal.SIGINT, clean_exit_handler)

# Define the status messages that indicate that a charging session is active
active_status_list = ['Charging', 'EVSEsuspended', 'EVsuspended', 'SuspendedEVSE', 'SuspendedEV', 'Faulted']

#desired sleep time should be equal to or greater than the controller step size to avoid excess computation
timestep = datetime.timedelta(seconds=step_size_sec)
sleep_time = 35
#Ensures sleep_time is less than or equal to the timestep defined at the beginning of the code
if sleep_time > step_size_sec:
    sleep_time = step_size_sec

####################################################
# define SCM Controller
time_index = pd.date_range(start=(datetime.datetime.now()-datetime.timedelta(hours=2)).strftime('%D %H:00:00'), end=(datetime.datetime.now()+datetime.timedelta(hours=23)).strftime('%D %H:00:00'), freq=timestep)
# create forecasted capacity from forecasted load
forecast = [0 for i in range(len(time_index))]
capacity_values = [total_capacity-f for f in forecast]
capacity_series = pd.Series(capacity_values, index=time_index)

# initialize the charging management system to be called as teach timestep
management_system = ChargingManagementSystem(capacity_series, allocation_method=scm_method) 
derms = DERMSComms(ip=derms_api_ip, username=username, password=password)
derms.active_statuses = active_status_list
derms.ess_list = ess_list 
derms.utility_meter_list = utility_meter_list
utility_meter_scale_factor = 1 # this is to pretend there are larger loads than there really are

# set up data recording
derms_measured = derms.get_measurements()
now_dt_string = datetime.datetime.now().strftime('%D_%H_%M_%S').replace('/','_')
output_file_name = f"derms_test_{now_dt_string}.csv"
with open(output_file_name, 'w') as csvfile:
    outputwriter = csv.writer(csvfile, delimiter=',')
    record_names = list(derms_measured.keys())
    record_names.insert(0, 'timestamp')
    outputwriter.writerow(record_names)
    derms_meas_values = list(derms_measured.values())
    derms_meas_values.insert(0,now_dt_string)
    outputwriter.writerow(derms_meas_values)

#####################################################
active_plugs = []
# Main controller loop. This loop will run at every step_size defined in the controller object. You only need to change/modify this loop based on your controller structure. 
def controller_loop(counter=0):
    updated_soc = []
    plugin = [] # list of evses with new plugin events
    plugout = [] # list of evses with new unplug events
    
    # read status from DERMS
    derms.detect_active_connectors()
    derms_measured = derms.get_measurements() # this is a dictionary of the measured values

    # get measured values in order to be recorded
    values_to_record = ['None' for i in record_names]
    values_to_record[0] = datetime.datetime.now().strftime('%D_%H_%M_%S').replace('/','_')
    for meas_name, meas_value in derms_measured.items():
        if meas_name in record_names:
            record_index = record_names.index(meas_name)
            values_to_record[record_index] = meas_value
        else:
            record_names.append(meas_name)
            values_to_record.append(meas_value)

    time_now = np.datetime64(derms_measured['time_meas'])
    time_now = time_now.astype(datetime.datetime)
    agg_load_emulation = 0      #Initialize agg_load_emulation as zero
    #Iterate over the utility_meter_list to sum power for all utility meters
    for utility_meter_id in derms.utility_meter_list:
        agg_load_emulation += derms_measured[f'utility_meter_{utility_meter_id}_P']/1e3

    # figure out which plugs are active via derms response
    for plug_name in plug_list:
        if plug_name+'_P' in derms_measured: # power is above 100W then a vehicle is plugged
            if plug_name not in active_plugs:
                active_plugs.append(plug_name)
                plugin.append(plug_name)
        elif plug_name in active_plugs: # if the power falls below 100W it's unplugged
            plugout.append(plug_name)
            active_plugs.remove(plug_name)

    # update the available capacity to be the total - load emulation 
    # find most recent time 
    latest_timestamp = capacity_series.index[capacity_series.index <= time_now]
    print(f'time_now: {time_now}, capacity_index[0]: {capacity_series.index[0]}')
    if latest_timestamp.size == 0:
        latest_timestamp = capacity_series.index[0]
    else:
        latest_timestamp = latest_timestamp[-1]
    # get just the building loads, not evse laods
    building_loads = 0
    building_loads += agg_load_emulation
    for plug_name in active_plugs:
        building_loads -= derms_measured[plug_name+'_P']/1e3
    print(f'Actual non-evse loads: {building_loads}')
    for cap_index in capacity_series.index:
        if cap_index >= latest_timestamp:
            capacity_series[cap_index] = total_capacity-building_loads*utility_meter_scale_factor
    management_system.capacity_series = capacity_series
    print(f'updated capacity: {management_system.capacity_series[latest_timestamp]} \n')

    # caluclate and send power limits
    print(f'active_plugs: {active_plugs}')
    if active_plugs != []:
        evse_powerlimits = management_system.update_timestep_control(plugin=plugin, unplug=plugout, time_now=time_now, timestep=timestep, soc_update=updated_soc) 

        for evse in evse_powerlimits.columns:
            # take the first value because it should be for this timestep
            power_limit = max(evse_powerlimits[evse][evse_powerlimits.index <= time_now].iloc[-1]*1000, 0) # convert to watts and send an int
            successful_put = derms.send_evse_power_limit(int(np.floor(power_limit)), evse)
            print(f'setting {evse} power limit to {power_limit} for timestep {time_now} \n')
            # make sure the value is recorded correctly
            limit_name = evse+'_limit'
            if limit_name in record_names:
                record_index = record_names.index(limit_name)
                values_to_record[record_index] = power_limit
            else:
                record_names.append(limit_name) 
                values_to_record.append(power_limit)
            # make sure the value is recorded correctly
        
    # record values in csv
    with open(output_file_name, 'a') as csvfile:
        outputwriter = csv.writer(csvfile, delimiter=',')
        outputwriter.writerow(values_to_record) 

    print()

# Main function
async def main():
    # Start logging
    counter = 0
    #datalogger.start()
    while True:
        controller_loop(counter)
        counter += 1
        await asyncio.sleep(step_size_sec)



asyncio.run(main())
import time
import signal
import sys
