from scm_module import SEMS, Controller, DataLogger, handle_interruption
import time
import signal
import sys
import asyncio

# Define the format of the comms. 
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
port_num=5555
sems = SEMS("user.broker.address", port_num, "SEMS", [("evse1/#", 0), ("EVSE2ABCD/#", 0), ("dcfc-123456/#", 0)], format)

# Define a controller object that takes a sems object and controller step size in seconds
controller = Controller(sems, step_size=5)

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

    controller.set.current('evse1', 25)
    controller.set.power('evse2', 5000)

    print()

# Main function
async def main():
    # Start logging
    datalogger.start()
    await controller.run(controller_loop)

# Run main function
asyncio.run(main())
