import paho.mqtt.client as mqttClient
import time
import datetime as dt
import os
import json
import traceback
from ast import literal_eval
from threading import Lock
import copy
import sys
import pandas as pd
import asyncio
import signal
from egauge_lib.egauge_comms2 import EgaugeComms2
import random
import pickle
import re

class SEMS:
    
    def __init__(self, broker_address, port, name, topic, format):

        self.broker_address = broker_address
        self.port = port
        self.name = name

        path = os.getcwd() + "\\logs"
        os.makedirs(path, exist_ok=True)
        filename = path + "\\sem-controller.log"
        self.controller_log_file = open(filename, "a")
        
        filename = path + "\\sem-mqtt.log"
        self.mqtt_log_file = open(filename, "a")

        filename = path + "\\sem-mqtt-rx.log"
        self.mqtt_rx_log_file = open(filename, "a")

        self.write_to_log("Controller session starting...")

        self.topic = topic

        self.connected = False
        self.client = mqttClient.Client(name) 
        self.received_message = dict()

        self.formatter = Formatter(format)

        self.ec = EgaugeComms2(ip="http://127.0.0.1", username="username", password="password")
        self.ec.connect()

    def connect(self):   
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.client.connect(self.broker_address, port=self.port)          #connect to broker

        self.client.subscribe(self.topic) 
        self.client.loop_start()

        while self.connected != True:    #Wait for connection
            time.sleep(0.1)

        self.write_to_log("Connected to MQTT Broker")

    # Command-line-interface (cli) log
    def cli_log(self, msg):
        output_str = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ": " + str(msg)
        print(output_str)
        return
    
    # Controller log 
    def controller_log(self,msg):
        output_str = dt.datetime.now().isoformat() + " : " + str(msg) + "\n"
        self.controller_log_file.write(output_str)
        return
    
    # Combined log function
    def write_to_log(self, msg):
        self.cli_log(msg)
        self.controller_log(msg)
        return   
         
    # MQTT log function. It displays the payload sent to each topic along with the corresponding timestamp.
    def mqtt_log(self, subtopic, mqtt_payload):
        output_str = dt.datetime.now().isoformat() + " : " + subtopic + "," + str(mqtt_payload) + "\n"
        self.mqtt_log_file.write(output_str)
        return
    
    def mqtt_rx_log(self, subtopic, mqtt_payload):
        output_str = dt.datetime.now().isoformat() + " : " + subtopic + "," + str(mqtt_payload) + "\n"
        self.mqtt_rx_log_file.write(output_str)
        return
    
    def send_mqtt_msg(self, subtopic, mqtt_payload):
        #print(self.topic.split('/')[0] + "/" + subtopic)
        path = subtopic 
        #print(path)
        return_code,msg_id  = self.client.publish(path, mqtt_payload)
        if return_code == mqttClient.MQTT_ERR_SUCCESS:
            self.mqtt_log(subtopic, mqtt_payload)
            self.controller_log("Sent MQTT msg: " + subtopic)

        else:
            self.controller_log("Failed to send MQTT msg: " + subtopic)
        return return_code    
       
    def on_message(self, client, userdata, msg):
        # self.update_controller_state(msg.topic, msg.payload)
        self.mqtt_rx_log(msg.topic, msg.payload.decode('utf-8'))
        self.received_message = self.formatter.decode(msg)
        #print(self.received_message)
        #print(f"Received message '{msg.payload.decode()}' on topic '{msg.topic}'")

    # Callback for when the client is (not) connected
    def on_connect(self, client, userdata, flags, rc):
    
        if rc == 0:
            #self.write_to_log("Connected to broker")
            self.connected = True                
    
        else:
            self.write_to_log("Connection failed")

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()
        self.write_to_log("Controller session ended.")
        self.controller_log_file.close()
        self.mqtt_log_file.close()
        self.mqtt_rx_log_file.close()

class Formatter:

    def __init__(self, format):
        self.format = format
        self.size = len(self.format)
        self.buffer = dict()
        for key in self.format:
            self.buffer[key] = None
        
    def decode(self, msg):
        for key in self.format:
            for topic in self.format[key]:
                if topic == msg.topic:
                    if self.format[key][topic] == 'bool':
                        self.buffer[key] = bool(int(msg.payload.decode()))
                    if self.format[key][topic] == 'str':
                        self.buffer[key] = str(msg.payload.decode())
                    if self.format[key][topic] == 'int':
                        self.buffer[key] = int(msg.payload.decode())
                    if self.format[key][topic] == 'float':
                        self.buffer[key] = float(msg.payload.decode())
                    if self.format[key][topic] == 'dict':
                        self.buffer[key] = json.loads(msg.payload.decode())
        
        return self.buffer

class Controller:
    class GetMethod:
        def __init__(self, sems, controller):
            self.sems = sems
            self.msg = None
            self.controller = controller
            self.measurements = {'time' : None,
                                 'evse1' : {'time' : None, 'power' : None, 'voltage' : None, 'current' : None, 'frequency' : None, 'energy' : None, 'soc' : None},
                                 'evse2' : {'time' : None, 'power' : None, 'voltage' : None, 'current' : None, 'frequency' : None, 'energy' : None, 'soc' : None},
                                 'dcfc' : {'time' : None, 'power' : None, 'voltage' : None, 'current' : None, 'frequency' : None, 'energy' : None, 'soc' : None}}

            self.last_status = {'evse1' : None, 'evse2' : None, 'dcfc' : None}

        def _decode_meas(self, evse):
            if evse == 'evse1':
                key = 'Metersevse1_P1'
            elif evse == 'evse2':
                key = 'Metersevse2_P1'
            elif evse == 'dcfc':
                key = 'Metersdcfc_P2'

            self.msg = self.sems.received_message

            #print(self.msg)
            if self.msg != {}  :
                if self.msg[key] is not None:
                    time = self.msg[key]['timestamp']
                    self.measurements['time'] = time
                    for elem in self.msg[key]['sampledValue']:
                        if elem['measurand'] == 'Power.Active.Import':
                            self.measurements[evse]['power'] = float(elem['value'])
                        elif elem['measurand'] == 'Voltage':
                            self.measurements[evse]['voltage'] = float(elem['value'])
                        elif elem['measurand'] == 'Current.Import':
                            self.measurements[evse]['current'] = float(elem['value'])
                        elif elem['measurand'] == 'Frequency':
                            self.measurements[evse]['frequency'] = float(elem['value'])
                        elif elem['measurand'] == 'Energy.Active.Import.Register':
                            self.measurements[evse]['energy'] = float(elem['value'])
                        elif elem['measurand'] == 'SoC':
                            self.measurements[evse]['soc'] = float(elem['value'])

        def status(self, evse):
            if evse == 'evse1':
                key = 'Statusevse1_P1'
            elif evse == 'evse2':
                key = 'Statusevse2_P1'
            elif evse == 'dcfc':
                key = 'Statusdcfc_P2'
            
            self.msg = self.sems.received_message

            if self.msg != {}:
                if key in self.msg and self.msg[key] is not None:
                    self.last_status[evse] = self.msg[key]['status']
                    return self.last_status[evse] 
                else:
                    return None
            else:
                return None
            
        def check_status(self, evse):
            if self.status(evse) in ['Preparing', 'Charging', 'EVSEsuspended', 'EVsuspended', 'SuspendedEVSE', 'SuspendedEV', 'Faulted']:
                return True
            else:
                return False

        def time(self, evse):
            #self._decode_meas(evse)
            #return self.measurements['time']
            return (dt.datetime.now())

        def voltage(self, evse):
            self._decode_meas(evse)
            return self.measurements[evse]['voltage'] if self.check_status(evse) else None

        def current(self, evse):
            self._decode_meas(evse)
            return self.measurements[evse]['current'] if self.check_status(evse) else None

        def power(self, evse):
            self._decode_meas(evse)
            return self.measurements[evse]['power'] if self.check_status(evse) else None

        def frequency(self, evse):
            self._decode_meas(evse)
            return self.measurements[evse]['frequency'] if self.check_status(evse) else None

        def soc(self, evse):
            self._decode_meas(evse)
            return self.measurements[evse]['soc'] if self.check_status(evse) else None

        def energy(self, evse):
            self._decode_meas(evse)
            return self.measurements[evse]['energy'] if self.check_status(evse) else None

        def counter(self):
            return self.controller.counter

        def sim_time(self):
            return self.controller.sim_time

    class SetMethod:
        def __init__(self, sems, controller):
            self.sems = sems
            self.controller = controller
            self.set_points = {'set_point_evse2' : None, 'set_point_evse1' : None, 'set_point_dcfc' : None}

        def power(self, evse, value):
            if self.controller.type == "power_limit":
                msg = {
                            "csChargingProfiles": {
                                                    "chargingSchedule" : {
                                                                            "chargingRateUnit" : 'W',
                                                                            "chargingSchedulePeriod" : {
                                                                                                            "limit" : value
                                                                                                       }
                                                                         }
                                                  }
                      }
            elif self.controller.type == "power_profile":
                msg = {
                            "csChargingProfiles": {
                                                    "chargingSchedule" : {
                                                                            "duration" : value['duration'],
                                                                            "chargingRateUnit" : 'W',
                                                                            "chargingSchedulePeriod" : df_to_ocpp(value['profile'])
                                                                         }
                                                  }
                      }
            
            payload = json.dumps(msg)

            if evse == 'evse1':
                if value != self.set_points['set_point_evse1']:
                    self.sems.send_mqtt_msg("evse1_plus/1/SetChargingProfile", payload)
                    self.set_points['set_point_evse1'] = value if self.controller.type == 'power_limit' else profile_to_list(value['profile'])
                else:
                    print("Set point of evse1 is the same as before, not updated!")
                    print(f"Set point (evse1): {value/1e3 if self.controller.type == 'power_limit' else value['profile'].to_string(index=False) } kW")
            elif evse == 'evse2':
                if value != self.set_points['set_point_evse2']:
                    self.sems.send_mqtt_msg("/1/SetChargingProfile", payload)
                    self.set_points['set_point_evse2'] = value if self.controller.type == 'power_limit' else profile_to_list(value['profile'])
                else:
                    print("Set point of evse2 is the same as before, not updated!")
                    print(f"Set point (evse2): {value/1e3 if self.controller.type == 'power_limit' else value['profile'].to_string(index=False)} kW")
            elif evse == 'dcfc':
                if value != self.set_points['set_point_dcfc']:
                    self.sems.send_mqtt_msg("dcfc-123456/2/SetChargingProfile", payload)
                    self.set_points['set_point_dcfc'] = value if self.controller.type == 'power_limit' else profile_to_list(value['profile'])
                else:
                    print("Set point of dcfc is the same as before, not updated!")
                    print(f"Set point (dcfc): {value/1e3 if self.controller.type == 'power_limit' else value['profile'].to_string(index=False)} kW")

            print(f"Power profile of\n{value if self.controller.type == 'power_limit' else value['profile'].to_string(index=False)} \n(W) has been sent to {evse}. \n")
                
        def current(self, evse, value):

            if self.controller.type == "power_limit":
                msg = {
                            "csChargingProfiles": {
                                                    "chargingSchedule" : {
                                                                            "chargingRateUnit" : 'A',
                                                                            "chargingSchedulePeriod" : {
                                                                                                            "limit" : value
                                                                                                       }
                                                                         }
                                                  }
                      }
            elif self.controller.type == "power_profile":
                if not isinstance(value, dict):
                    raise TypeError("Value argument must be a dictionary for this controller type!")
                msg = {
                            "csChargingProfiles": {
                                                    "chargingSchedule" : {
                                                                            "duration" : value['duration'],
                                                                            "chargingRateUnit" : 'A',
                                                                            "chargingSchedulePeriod" : df_to_ocpp(value['profile'])
                                                                         }
                                                  }
                      }

            payload = json.dumps(msg)

            if evse == 'evse1':
                if value != self.set_points['set_point_evse1']:
                    self.sems.send_mqtt_msg("evse1_plus/1/SetChargingProfile", payload)
                    self.set_points['set_point_evse1'] = value if self.controller.type == 'power_limit' else profile_to_list(value['profile'])
                else:
                    print("Set point of evse1 is the same as before, not updated!")
                    print(f"Set point (evse1): {value if self.controller.type == 'power_limit' else value['profile'].to_string(index=False)} A")
            elif evse == 'evse2':
                if value != self.set_points['set_point_evse2']:
                    self.sems.send_mqtt_msg("EVSE2ABCD/1/SetChargingProfile", payload)
                    self.set_points['set_point_evse2'] = value if self.controller.type == 'power_limit' else profile_to_list(value['profile'])
                else:
                    print("Set point of evse2 is the same as before, not updated!")
                    print(f"Set point (evse2): {value if self.controller.type == 'power_limit' else value['profile'].to_string(index=False)} A")
            elif evse == 'dcfc':
                if value != self.set_points['set_point_dcfc']:
                    self.sems.send_mqtt_msg("dcfc-123456/2/SetChargingProfile", payload)
                    self.set_points['set_point_dcfc'] = value if self.controller.type == 'power_limit' else profile_to_list(value['profile'])
                else:
                    print("Set point of dcfc is the same as before, not updated!")
                    print(f"Set point (dcfc): {value if self.controller.type == 'power_limit' else value['profile'].to_string(index=False)} A")

            print(f"Current profile of\n{value if self.controller.type == 'power_limit' else value['profile'].to_string(index=False)} \n(A) has been sent to {evse}.\n")

    def __init__(self, sems, step_size=5, type="power_limit"):
        self.sems = sems
        self.get = self.GetMethod(sems, self)
        self.set = self.SetMethod(sems, self)
        self.step_size = step_size
        self.counter = 0
        self.sim_time = 0
        self.type = type

    async def run(self, controller_loop):
        
        while True:
            controller_loop()
            self.counter += 1
            self.sim_time = (self.counter) * self.step_size
            await asyncio.sleep(self.step_size)

class DataLogger:
    def __init__(self, controller, period = 5):
        self.period = period
        self.running = False
        self.controller = controller
        self.data = dict()
        self.data['counter'] = list()
        self.data['sim_time'] = list()
        self.data['time'] = list()
        self.data['time_ocpp'] = list()
        self.data['evse1_voltage'] = list()
        self.data['evse1_current'] = list()
        self.data['evse1_power'] = list()
        self.data['evse1_soc'] = list()
        self.data['evse1_frequency'] = list()
        self.data['evse1_energy'] = list()
        self.data['evse1_status'] = list()
        self.data['evse2_voltage'] = list()
        self.data['evse2_current'] = list()
        self.data['evse2_power'] = list()
        self.data['evse2_soc'] = list()
        self.data['evse2_frequency'] = list()
        self.data['evse2_energy'] = list()
        self.data['evse2_status'] = list()
        self.data['dcfc_voltage'] = list()
        self.data['dcfc_current'] = list()
        self.data['dcfc_power'] = list()
        self.data['dcfc_soc'] = list()
        self.data['dcfc_frequency'] = list()
        self.data['dcfc_energy'] = list()
        self.data['dcfc_status'] = list()
        self.data['set_point_evse1'] = list()
        self.data['set_point_evse2'] = list()
        self.data['set_point_dcfc'] = list()
        self.data['load_power'] = list()
        self.data['panel_power'] = list()

    async def _get_measurements(self):
        self.data['counter'].append(self.controller.get.counter())
        self.data['sim_time'].append(self.controller.get.sim_time())
        self.data['time'].append(dt.datetime.now())
        self.data['time_ocpp'].append(self.controller.get.time('evse1'))

        self.data['evse1_status'].append(self.controller.get.status('evse1'))
        self.data['evse1_voltage'].append(self.controller.get.voltage('evse1'))
        self.data['evse1_current'].append(self.controller.get.current('evse1'))
        self.data['evse1_power'].append(self.controller.get.power('evse1'))
        self.data['evse1_soc'].append(self.controller.get.soc('evse1'))
        self.data['evse1_frequency'].append(self.controller.get.frequency('evse1'))
        self.data['evse1_energy'].append(self.controller.get.energy('evse1'))

        self.data['evse2_status'].append(self.controller.get.status('evse2'))
        self.data['evse2_voltage'].append(self.controller.get.voltage('evse2'))
        self.data['evse2_current'].append(self.controller.get.current('evse2'))
        self.data['evse2_power'].append(self.controller.get.power('evse2'))
        self.data['evse2_soc'].append(self.controller.get.soc('evse2'))
        self.data['evse2_frequency'].append(self.controller.get.frequency('evse2'))
        self.data['evse2_energy'].append(self.controller.get.energy('evse2'))
        
        self.data['dcfc_status'].append(self.controller.get.status('dcfc'))
        self.data['dcfc_voltage'].append(self.controller.get.voltage('dcfc'))
        self.data['dcfc_current'].append(self.controller.get.current('dcfc'))
        self.data['dcfc_power'].append(self.controller.get.power('dcfc'))
        self.data['dcfc_soc'].append(self.controller.get.soc('dcfc'))
        self.data['dcfc_frequency'].append(self.controller.get.frequency('dcfc'))
        self.data['dcfc_energy'].append(self.controller.get.energy('dcfc'))
        
        self.data['set_point_evse1'].append(self.controller.set.set_points['set_point_evse1'])
        self.data['set_point_evse2'].append(self.controller.set.set_points['set_point_evse2'])
        self.data['set_point_dcfc'].append(self.controller.set.set_points['set_point_dcfc'])
        self.data['load_power'].append(self.controller.sems.ec.get_measurements()['Load_P'])
        self.data['panel_power'].append(self.controller.sems.ec.get_measurements()['Panel_P'])

    def _len_check_and_pad(self):
        data_length = len(self.data['time'])
        egauge_data_length = len(self.data['load_power'])
        if data_length > egauge_data_length:
            for i in range(0, data_length - egauge_data_length):
                self.data['load_power'].append(self.data['load_power'][-1])
        elif data_length > egauge_data_length:
            # We can augment the meter data as well if it has less samles, which is unlikely
            None
        else:
            None

    def stop(self):
        self.running = False
        path = os.getcwd() + "\\data"
        os.makedirs(path, exist_ok=True)
        current_time_date = dt.datetime.now()
        filename = path + "\\charging_test_data - " + current_time_date.strftime("%Y_%m_%d-%H_%M_%S")
        self._len_check_and_pad()
        with open(filename + '.pickle', 'wb') as f:
            pickle.dump(self.data, f)
        df = pd.DataFrame(self.data)
        df.to_csv(filename + ".csv")

    async def _run(self):
        while self.running:
            await self._get_measurements()
            #print(self.data)
            await asyncio.sleep(self.period)

    def start(self):
        self.running = True
        asyncio.create_task(self._run())

def handle_interruption(sems: SEMS, datalogger : DataLogger = None, controller : Controller = None):
    def signal_handler(sig, frame):
        print('You pressed Ctrl+C! All comms and logging have been stopped!')
        # Perform any cleanup here if necessary
        
        if controller is not None:
            controller.type = "power_limit"
            controller.set.power('evse1', 0) 
            controller.set.power('evse2', 0)
            controller.set.power('dcfc', 0)
        if datalogger is not None:
            datalogger.stop()

        sems.close()
        sys.exit(0)

    # Register the signal handler for SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, signal_handler)
       
def df_to_ocpp(value : pd.DataFrame):
    ocpp_msg = list()
    for index, row in value.iterrows():
        ocpp_msg.append({
                            'startPeriod' : row['start_period'],
                            'limit' : row['limit']
                        })
    return ocpp_msg
        
def parse_string_to_tuples(input_str : str):
    # Use regular expressions to find all tuples in the string
    tuple_list = re.findall(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", input_str)
    
    # Convert matches to a list of tuples with integers
    return [(int(x), int(y)) for x, y in tuple_list]       

def list_to_profile(tupple_list : list):
    df = pd.DataFrame(columns=["start_period", "limit"])
    for i in tupple_list:
        new_rows = pd.DataFrame([[i[0], i[1]]], columns=["start_period", "limit"])
        df = pd.concat([df, new_rows], ignore_index=True)
    
    return df

def profile_to_list(df : pd.DataFrame):
    charging_profile = list()
    for index, row in df.iterrows():
        charging_profile.append((row['start_period'], row['limit']))

    return charging_profile

def manual_set(controller):
    print(f"""Enter setpoints with the following format: <evse> <a or w> <value>
    evse     : evse1 or evse2 or dcfc
    a or w   : amps or watt
    value    : charging current or power
    examples : enter "evse2 a 20" or "evse1 w 2500" without quotation marks ("")\n""")
        
    user_input = input("Enter setpoints : ")
    try:
        values = user_input.split()
        x, y, z = values

        if y.lower() == 'a':
            controller.set.current(x.lower(), int(z))
        elif y.lower() == 'w':
            controller.set.power(x.lower(), int(z))
        print()
    except:
        pass
        
def manual_set_chr_profile(controller):
    print(f"""================================================================================================================
    Enter charging profiles with the following format: <evse> <a or w> <[(start_period1, limit1), (start_period2, limit2), ...]>
    evse       : evse1 or evse2 or dcfc
    a or w     : amps or watt      
    limit      : power limit in w 
    examples   : enter "evse2 w [(0, 2000), (500, 5000), (1000, 7500)]" or "evse1 a [(0, 20), (500, 50), (1000, 30)]" \n\t\t without quotation marks ("")\n""")

    user_input = input("Enter the profile : ")
    index = user_input.find('[')
    try:
        evse, type = (user_input[:index].strip()).split()
        tuple_part = user_input[index:]    
        profile = parse_string_to_tuples(tuple_part)
        print()

        df_profile = list_to_profile(profile)
        payload = {
            'duration' : 3600,
            'profile' : df_profile
        }

        if type.lower() == 'a':
            controller.set.current(evse, payload)
            print("Current value sent")
        elif type.lower() == 'w':
            controller.set.power(evse, payload)

    except:
        pass

