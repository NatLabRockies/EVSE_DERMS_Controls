from scm_module import SEMS, Controller, DataLogger, handle_interruption, list_to_profile
import time
import datetime
import signal
import sys
import asyncio
import pandas as pd
import numpy as np

# Define the format of the comms. 
# This will depend on the MQTT name of the EVSE and may take different formats
format = {
    'Heartbeatevse1' : {'evse1/last_heartbeat' : 'str'},
    'IsChargingevse1' : {'evse1/Charging' : 'bool'},
    'Statusevse1_P1' : {'evse1/1/StatusNotification' : 'dict'},
    'Metersevse1_P1' : {'evse1/1/MeterValues/' : 'dict'},
    'IsChargingevse2' : {'EVSE2ABCD/Charging' : 'bool'},
    'Statusevse2_P1' : {'EVSE2ABCD/1/StatusNotification' : 'dict'},
    'Metersevse2_P1': {'EVSE2ABCD/1/MeterValues/' : 'dict'},
    'IsChargingdcfc' : {'dcfc-123456/Charging' : 'bool'},
    'Statusdcfc_P2' : {'dcfc-123456/2/StatusNotification' : 'dict'},
    'Metersdcfc_P2': {'dcfc-123456/2/MeterValues/' : 'dict'},
}
# Define Smart Energy Management System (SEMS) object that handles all the MQTT comms with the OCPP
port_num = 5555
sems = SEMS("user.broker.address", port_num, "SEMS", [("evse1/#", 0), ("EVSE2ABCD/#", 0), ("dcfc-123456/#", 0)], format)

# Define a controller object that takes a sems object and controller step size in seconds
controller = Controller(sems, step_size=5, type='power_profile')

# Define a datalogger object that takes a controller object and period in seconds
datalogger = DataLogger(controller, period=5)

# Connect to the mqtt server
sems.connect()

# Handle user interruption Ctrl+C, stop coms and data-logging
handle_interruption(sems, datalogger, controller)

# Main controller loop. This loop will run at every step_size defined in the controller object. You only need to change/modify this loop based on your controller structure. 
def controller_loop():
    print(f"######## TIME : {controller.get.time('evse1')} ########")
    print(f"Loop counter : {controller.get.counter()}")
    print(f"evse1 status: {controller.get.status('evse1')}")
    print(f"evse1 voltage: {controller.get.voltage('evse1')}")
    print(f"evse1 power: {controller.get.power('evse1')}")
    print(f"evse1 current: {controller.get.current('evse1')}")
    print(f"evse1 frequency: {controller.get.frequency('evse1')}")
    print(f"evse1 energy: {controller.get.energy('evse1')}")
    print(f"evse1 soc: {controller.get.soc('evse1')}")
    print()
    evse2_time = controller.get.time('evse2')
    print(f"######## TIME : {evse2_time} ########")
    print(f"evse2 status: {controller.get.status('evse2')}")
    print(f"evse2 voltage: {controller.get.voltage('evse2')}")
    print(f"evse2 power: {controller.get.power('evse2')}")
    print(f"evse2 current: {controller.get.current('evse2')}")
    print(f"evse2 frequency: {controller.get.frequency('evse2')}")
    print(f"evse2 energy: {controller.get.energy('evse2')}")
    print(f"evse2 soc: {controller.get.soc('evse2')}")
    print()
    print(f"dcfc status: {controller.get.status('dcfc')}")
    print(f"dcfc voltage: {controller.get.voltage('dcfc')}")
    print(f"dcfc power: {controller.get.power('dcfc')}")
    print(f"dcfc current: {controller.get.current('dcfc')}")
    print(f"dcfc frequency: {controller.get.frequency('dcfc')}")
    print(f"dcfc energy: {controller.get.energy('dcfc')}")
    print(f"dcfc soc: {controller.get.soc('dcfc')}")
    print()

    # list_to_profile function helps you generate a profile payload out of a list of tuples in the following format
    # [(start_period1, limit1), (start_period2, limit2), ...]
    # duration is the total duration of the charging profile in seconds
    example_profile = [(0, 2000), 
                        (30, 5000),
                        (60, 7500),
                        (90, 5000),
                        (120, 2000), 
                        (150, 5000),
                        (180, 7500),
                        (210, 5000), 
                        (240, 2000),
                        (270, 5000),
                        (300, 7500),
                        (330, 5000), 
                        (360, 2000),
                        (390, 5000)]

    controller.set.current('evse1', {'duration' : 3600, 'profile' : list_to_profile([(0, 20), 
                                                                                      (30, 30), 
                                                                                      (60, 40),
                                                                                      (90,30),
                                                                                      (120,20),
                                                                                      (150,30)])})
    
    # if evse2_time.minute < 32: #uncomment  this if statement if you want to stop sending profiles after a given time
    evse2_seconds = evse2_time.second+np.remainder(evse2_time.minute,5)*60
    evse2_profile = [(0,2000)]
    for setpoint in example_profile:
        if setpoint[0]>evse2_seconds:
            evse2_profile.append((setpoint[0]-evse2_seconds,setpoint[1]))
        else:
            first_setpoint = setpoint[1]
            evse2_profile[0] = (0,first_setpoint)
    
    controller.set.power('evse2', {'duration' : evse2_profile[-1][1], 'profile' : list_to_profile(evse2_profile)})

    print()

# Main function
async def main():
    # this runs every controller period
    # Start logging
    datalogger.start()
    await controller.run(controller_loop)

# Run main function
asyncio.run(main())


## comment this out if you don't want to kill the connection
#async def cut_controls(sleep_time=90):
#    #this function closes the connection, but leaves the datalogger so that we can observe it change the profile.
#    asyncio.sleep(sleep_time)
#    sems.close()
#    for task in asyncio.Task.all_tasks():
#        task.cancel()
#    #sys.exit(0)

#asyncio.run(cut_controls(sleep_time=120))