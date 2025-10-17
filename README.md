# FUSE_SCM
An MQTT (Message Queuing Telemetry Transport) and OCPP (Open Charge Point Protocol) based remote smart charging controller framework for AC Electric Vehicle Supply Equipments (EVSEs). The code in this repo allows for NREL controls to interface with the real Distrubeted Energy Resource Managaement System (DERMS) and EVSEs in NRELs ESIF Optimization and Control Laboratory (OCL). Different charge management algorithms can be tested to determine which power allocation method is most effective with the overall goal of demonstrating clear and well documented test results as well as providing functional control algorithms which could be utilized to provide effective smart charge management (SCM) at EV charging stations. Different power allocation methods are programmed in lab_demo_controller.py and include allocation based on first come first served, equal sharing, state of charge (SOC), priority factors, and behind the meter control methods. 

## Running DERMS Integrated Controls
The scripts are intended to be run on a machine which has permissions for DERMS communication. 
The main script users will run is example_derms.py.

## Overview of Primary Scripts

### example_derms.py
This script utilizes the ChargingManagementSystem class from lab_demo_controller.py and DERMSComms class from derms_lib.derms_comms.py to run tests using different power allocation methods. This script tracks EV plugin and unplug events and outputs a csv file containing EVSE power limits, EVSE power and voltage read at each timestep, meter power and voltage at each timestep, and stationary Energy Storage System (ESS) power, voltage, and SOC at each timestep.

**User Inputs:**
- plug_list should be updated with a list of names of EVSEs at a controlled site
- step_size_sec Update with desired step size, this should be longer than it takes for the DERMS to update the EVSE power level reading
- allocation_method Update with the desired power allocation method to be used when calling the ChargingManagement System class
- derms.ess_list Update with ESS IDs when there are ESS units present on site
- derms.utility_meter_list Update with exact utility meter ids to match DERMS API naming convention

### derms_comms.py
This script is located in the derms_lib folder. It detects which connectors are active at each EVSE, sends EVSE power limits and power profiles, and gets measurements of voltage and power at each time step for each connected EVSE port and for the meter.

**User Inputs:**  
- Since this is called from example_derms.py and not called directly, inputs are passed along from the example_derms script

### lab_demo_controller.py
The primary function of this script is to create a ChargingManagementSystem class which defines different power allocation methods which can be used to test different smart charge management approaches. This script also defines an EV class and ChargingStation class which tracks which EVs are connected and when EVs are added/removed from a charging station.

**User Inputs:**  
- Since this is called from example_derms.py and not called directly, inputs are passed along from the example_derms script

# Contacts
For questions or more information, please contact: 

* Nadia Panossian: nadia.panossian@nrel.gov
