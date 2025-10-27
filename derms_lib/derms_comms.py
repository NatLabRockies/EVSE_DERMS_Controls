
from datetime import datetime, timezone, timedelta

import json

import os
import sys

import requests

"""
This file sets up a DERMS communications class which
establishes which EVSE and ports are active, 
reads in meter values for connected EVSE and other site loads
and processes those loads for the controller to handle in another script
This class also handles the API calls for clearing a charge profile,
setting a charge limit, and setting a charge profile on the DERMS

A successful API call will return the response 200, so several blocks check for this
"""

class DERMSComms():
    def __init__(self, ip='http://127.0.0.1:5555/json/reply/ReadApplicationPointWebRequest', username='username', password='password') -> None:
        self.query_string = ""
        self.derms_api = ip # os.getenv("EGDEV", ip)
        self.derms_user = username #os.getenv("EGUSR", username)
        self.derms_password = password #os.getenv("EGPWD", password)
        self.json_format = {"Content-Type":"application/json"} # format of API response
        self.active_statuses = ["Charging", "SuspendedEVSE", "SuspendedEV", "Faulted"] 
        # SuspendedEVSE is when there's a smart charge limitation or hardware limitation preventing charging, but it's plugged
        # 
        # SuspendedEV is when the EVSE can supply current, but whatever is plugged in can't take a charge
        # Faulted is when any error between EV and EVSE prevents charging

        self.connected : bool
        self.evse_to_endpoint_keys = {'abb':"EVSE0", 'pulsar_plus':"EVSE1"}
        self.active_connectors = {} #'abb':[0,1], 'pulsarplus':[0,1]
        self.ess_list = []  #Initialize ess_list as an empty list
        self.utility_meter_list = [] #Initialize utility_meter_list as an empty list

    def detect_active_connectors(self):
        # figure out how many connectors are active at each evse
        # loop through 0 to 7 (upper limit on gateway, this is a spatial constraint, can only have so many vehicles parked)
        self.active_connectors = {}
        for evse_id in self.evse_to_endpoint_keys.keys():
            # reset it each time
            active_connectors = []
            # there are 0 to 4 potential ports at each EVSE, so loop through them
            # if an API response is recieved from the port, then 
            # check the status of the port to see if it should be added to the
            # list of active ports which are used in the controls
            for i_connector in range(3):
                endpoint = "{\"Name\": \"ANM.OCPP."+str(self.evse_to_endpoint_keys[evse_id])+".CONNECTOR"+str(i_connector)+".MeterValues\"}"
                request_response = requests.request(method='POST', url=self.derms_api, auth=(self.derms_user,self.derms_password), data=endpoint, json=self.json_format)
                response_json = request_response.json()
                #print(response_json)
                if not 'Success' in response_json.keys():
                    # this indicates either there is no connector at this id, or nothing is plugged
                    pass
                else:
                    #if response_json['Success'] == True and not response_json['StringValue'] == '':
                    #    # now check to see if the status is charging
                    status_endpoint = endpoint.replace('MeterValues', 'StatusNotification')
                    request_response = requests.request(method='POST', url=self.derms_api, auth=(self.derms_user,self.derms_password), data=status_endpoint, json=self.json_format)
                    response_json = request_response.json()
                    print(response_json)
                    if not response_json['StringValue'] == '' and json.loads(response_json['StringValue'])['status'] in self.active_statuses:
                        # this indicates a vehicle is plugged and connector is active
                        active_connectors.append(i_connector)
                    else:
                        print(f'evse: {evse_id} connector {i_connector} not active')
                    #else:
                    #    print(f'evse: {evse_id} connector {i_connector} may exist, but not connected') 
            if len(active_connectors)>0:
                self.active_connectors[evse_id] = active_connectors
        print(f'Active connectors detected: {self.active_connectors}')

        
    def get_measurements(self, print_out = True):
        # queries endpoints in the DERMS 
        endpoints = []
        meas_vars = dict()
        meas_vars['time_meas'] = datetime.today()

        #utility_meter_endpoint_voltage = "{\"Name\": \"MEMORY.SGX.DEVICES.5.CAPABILITIES.MEASUREMENT.STATUS.V\"}" # replace with P, or VA as needed
        ##utility_meter_endpoint_aparent = "{\"Name\": \"MEMORY.SGX.DEVICES.5.CAPABILITIES.MEASUREMENT.STATUS.VA\"}" # VA doesn't recieve a response
        #utility_meter_endpoint_real = "{\"Name\": \"MEMORY.SGX.DEVICES.5.CAPABILITIES.MEASUREMENT.STATUS.P\"}"
        # EVSE's take the OCPP format with connection point names following style: ANM.OCPP.EVSE2.CONNECTOR1.METERVALUES
        # get any start transaction notification

        # create a list of power, voltage, and status endpoints for all active evse and their connectors
        for evse_id in self.active_connectors.keys():
            for connector_id in self.active_connectors[evse_id]:
                #voltage_key = f"MEMORY.ANM.DEVICES.{self.evse_to_endpoint_keys[evse_id]}.CONNECTOR{connector_id}.VOLTAGE.VALUE"
                #evse_endpoint_voltage = "{'Name':"+voltage_key+"}"
                #endpoints.append(evse_endpoint_voltage)
                ## OCPP version: f"ANM.OCPP.{self.evse_to_endpoint_keys[evse.lower()]}.CONNECTOR{connector}.MeterValues"
                #power_key = f"MEMORY.ANM.DEVICES.{self.evse_to_endpoint_keys['abb']}.CONNECTOR{connector_id}.WATT_IMPORT.VALUE"
                #evse_endpoint_real = "{'Name':" + power_key + "}" 
                #endpoints.append(evse_endpoint_real)
                # initialize power and voltage points in case it's not plugged
                ###### NOTE: These values are all in W, so need to divide by 1000 to get kW ######
                meas_vars[evse_id.upper()+'_P'] = 0 # default power is 0 W, this is updated below
                meas_vars[evse_id.upper()+'_V'] = 240 # default voltage for L2 is 240V, this is updated below
                # create a key to get the actual values from the connector
                meter_key = f"ANM.OCPP.{self.evse_to_endpoint_keys[evse_id]}.CONNECTOR{connector_id}.MeterValues"
                endpoint = "{\"Name\": \"" + meter_key + "\"}" 
                endpoints.append(endpoint)
                request_response = requests.request(method='POST', url=self.derms_api, auth=(self.derms_user,self.derms_password), data=endpoint, json=self.json_format)
                response_json = request_response.json()
                endpoint_name = response_json['Name'] #
                # if you get a successful API response from the DERMS and that response has a value string, get the power and voltage from the response
                if response_json['Success'] == True and not response_json['StringValue'] == '':
                    sampled_values = json.loads(response_json['StringValue'])['meterValue'][0][0]['sampledValue']
                    for sampled_value in sampled_values:
                        if sampled_value['measurand'] == "Power.Active.Import":
                            meas_vars[evse_id.upper()+'_P'] = sampled_value['value']
                        elif sampled_value['measurand'] == "Voltage":
                            meas_vars[evse_id.upper()+'_V'] = sampled_value['value']
                    #meas_vars[evse_id.upper()+'_P'] = json.loads(response_json['StringValue'])['meterValue'][0][0]['sampledValue']
                    #meas_vars[evse_id.upper()+'_V'] = json.loads(response_json['StringValue'])['VOLTAGE']
                    self.connected = True
                    response_time = int(response_json['Timestamp'].replace('/Date(','').split('-')[0])/1000 # convert from 13 digit unix to unix format understood by datetime
                    dt = datetime.fromtimestamp(response_time, timezone.utc) # this is the time that you read the value from DERMS, not the time the value was updated on the DERMS
                    #if endpoint == utility_meter_endpoint_real:
                    time_measured = dt
                    meas_vars['time_meas'] = time_measured
                else:
                    print(f"{endpoint_name} not retrieved, not updating value")
                    print(f"response recieved: {response_json}")

                if print_out and response_json['Success']:
                    print(f"\nMeasuremets as of {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (meter time)\n")
                    print(f"{endpoint} value is {response_json['AnalogValue']}")
        
        #Iterates over the utility_meter_list which is inputted in example_derms with utility meters on specific site when the DERMSComms object is created to get voltage and power measurements
        for utility_meter_id in self.utility_meter_list:
            # next get the utility meter power
            utility_meter_key_power = f"{{\"Name\": \"SGX.{utility_meter_id}.CAPABILITIES.MEASUREMENT.STATUS.P\"}}"
            request_response = requests.request(method='POST', url=self.derms_api, auth=(self.derms_user,self.derms_password), data=utility_meter_key_power, json=self.json_format)
            response_json = request_response.json()
            if response_json['Success'] == True:
                meas_vars[f'utility_meter_{utility_meter_id}_P'] = response_json['AnalogValue']
            else:
                meas_vars[f'utility_meter_{utility_meter_id}_P'] = 0
            # get utility meter voltage
            utility_meter_key_voltage = f"{{\"Name\": \"SGX.{utility_meter_id}.CAPABILITIES.MEASUREMENT.STATUS.V\"}}"
            request_response = requests.request(method='POST', url=self.derms_api, auth=(self.derms_user,self.derms_password), data=utility_meter_key_voltage, json=self.json_format)
            response_json = request_response.json()
            if response_json['Success'] == True:
                meas_vars[f'utility_meter_{utility_meter_id}_V'] = response_json['AnalogValue']
            else:
                meas_vars[f'utility_meter_{utility_meter_id}_V'] = 240

            if print_out:
                print("\n")
                for measured in meas_vars.keys():
                    if measured.endswith('_P'):
                        print(f"{measured} (kW): {meas_vars[measured]/1e3}")
                print("\n")

        #Iterates over the ess_list (which must be inputted in example_derms with ESS units for the specific site) to pull power, soc, and voltage for each ESS unit
        for ess_id in self.ess_list:
            #Creates identifiers to later query the DERMS API to pull ESS outputs
            ###NOTE these identifiers must be updated to exactly match the DERMS API naming conventions
            ess_power_key = f"ANM.ESS.{ess_id}.Power"
            ess_voltage_key = f"ANM.ESS.{ess_id}.Voltage"
            ess_soc_key = f"ANM.ESS.{ess_id}.SOC"
            
            #Query Power
            power_endpoint = "{\"Name\": \"" + ess_power_key + "\"}" 
            request_response = requests.request(method='POST', url=self.derms_api, auth=(self.derms_user,self.derms_password), data=power_endpoint, json=self.json_format)
            response_json = request_response.json()
            if response_json['Success'] == True:
                ###NOTE 'AnalogValue' must be updated with the actual key to the power value from the API
                meas_vars[ess_id.upper()+'_P'] = response_json['AnalogValue']
            else:
                print("No ESS power detected. A possible communication error may have occurred.")
                #meas_vars[ess_id.upper()+'_P'] = 0     #Do you want this line instead?
            
            #Query Voltage
            voltage_endpoint = "{\"Name\": \"" + ess_voltage_key + "\"}" 
            request_response = requests.request(method='POST', url=self.derms_api, auth=(self.derms_user,self.derms_password), data=voltage_endpoint, json=self.json_format)
            response_json = request_response.json()
            if response_json['Success'] == True:
                ###NOTE 'AnalogValue' must be updated with the actual key to the voltage value from the API
                meas_vars[ess_id.upper()+'_V'] = response_json['AnalogValue']
            else:
                print("No ESS voltage detected. A possible communication error may have occurred.")
                #meas_vars[ess_id.upper()+'_V'] = 240     #Do you want this line instead?
            
            #Query State of Charge
            soc_endpoint = "{\"Name\": \"" + ess_soc_key + "\"}" 
            request_response = requests.request(method='POST', url=self.derms_api, auth=(self.derms_user,self.derms_password), data=soc_endpoint, json=self.json_format)
            response_json = request_response.json()
            if response_json['Success'] == True:
                ###NOTE 'AnalogValue' must be updated with the actual key to the SOC value from the API
                meas_vars[ess_id.upper()+'_SOC'] = response_json['AnalogValue']
            else:
                print("No ESS SOC detected. A possible communication error may have occurred.")
                #meas_vars[ess_id.upper()+'_SOC'] = 0     #Do you want this line instead?

        return meas_vars

    def send_evse_power_limit(self, power_limit=11500, evse='ABB', connector=1, print_out=True):
        # send power limit in kW to the evse and connector by name
        evseid = self.evse_to_endpoint_keys[evse.lower()]
        #endpoint = {"MEMORY.SGX.DEVICES.4.CAPABILITIES.MEASUREMENT.STATUS.P": power_limit*1e3}
        # OCPP 1.6 format: MessageTypeId, UniqueId
        # the string below is a json formatted in OCPP1.6 with escapes such that the " " get added and sent via the API properly
        # several of the values are standard for EVSE profile limits including the 2 defining the message type. The stackLevel is the priority. Duration is given in seconts
        # the API call sends the profile string value as the endpoint string value
        profile_str_value = "[2,\"123\",\"SetChargingProfile\",{\"connectorId\":"+str(connector)+",\"csChargingProfiles\":{\"chargingProfileId\":123,\"stackLevel\":1,\"chargingProfilePurpose\":\"TxDefaultProfile\",\"chargingProfileKind\":\"Absolute\",\"recurrencyKind\":\"Daily\",\"validFrom\":\""+datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')+"\",\"validTo\":\""+ (datetime.now()+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')+"\",\"chargingSchedule\":{\"duration\":86400,\"startSchedule\":\""+datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')+"\",\"chargingRateUnit\":\"W\",\"chargingSchedulePeriod\":[{\"startPeriod\":0,\"limit\":"+str(power_limit)+"}],\"minChargingRate\":0.0}}}]"
        # try replacing TxDefaultProfile above with TxProfile or Default
        endpoint = {"Name":f"ANM.OCPP.{evseid}.SetChargingProfile",
        "StringValue":profile_str_value}
        endpoint_json = json.dumps(endpoint)
        json_format = {"Content-Type":"application/json"}
        request_response = requests.request(method='POST', url=self.derms_api.replace('Read','Write'), auth=(self.derms_user, self.derms_password), data = endpoint_json, json=json_format)
        
        if request_response == '200':
            if print_out:
                print(request_response)
            return True
        else:
            return False

    def send_evse_power_profile(self, power_profile=[], profile_timestamps=[], evse='ABB', connector=1, print_out=True):
        # send a full profile instead of just one setpoint
        evseid = self.evse_to_endpoint_keys[evse.lower()]
        charging_schedule = []
        for ts in range(len(profile_timestamps)):
            charging_schedule.append({"startPeriod":profile_timestamps[ts], "limit": power_profile[ts]})        
        # OCPP 1.6 format: MessageTypeId, UniqueId
        # this json OCPP1.6 formatted string is similar to the one in send_evse_power_limit, but it 
        # includes the power limits for a profile, and so has a list of charging schedule data
        profile_str_value = "[2,\"123\",\"SetChargingProfile\",{\"connectorId\":"+str(connector)+",\"csChargingProfiles\":{\"chargingProfileId\":123,\"stackLevel\":1,\"chargingProfilePurpose\":\"TxDefaultProfile\",\"chargingProfileKind\":\"Absolute\",\"recurrencyKind\":\"Daily\",\"validFrom\":\""+datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')+"\",\"validTo\":\""+ (datetime.now()+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')+"\",\"chargingSchedule\":{\"duration\":86400,\"startSchedule\":\""+datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')+"\",\"chargingRateUnit\":\"W\",\"chargingSchedulePeriod\":"+charging_schedule+",\"minChargingRate\":0.0}}}]"
        # try replacing TxDefaultProfile above with TxProfile or Default
        endpoint = {"Name":f"ANM.OCPP.{evseid}.SetChargingProfile",
        "StringValue":profile_str_value}
        endpoint_json = json.dumps(endpoint)
        json_format = {"Content-Type":"application/json"}
        request_response = requests.request(method='POST', url=self.derms_api.replace('Read','Write'), auth=(self.derms_user, self.derms_password), data = endpoint_json, json=json_format)
        
        if request_response == '200':
            if print_out:
                print(request_response)
            return True
        else:
            return False

    def clear_evse_power_limit(self, evse='ABB', connector=1):
        # clear any power limits from the evse by name
        evseid = self.evse_to_endpoint_keys[evse.lower()]

        #endpoint = {"MEMORY.SGX.DEVICES.4.CAPABILITIES.MEASUREMENT.STATUS.P": power_limit*1e3}
        endpoint = {"Name":f"ANM.OCPP.{evseid}.ClearChargingProfile",
            "StringValue":"[2,\"123\", \"ClearChargingProfile\", {\"connectorId\":"+str(connector)+"}]"}
        endpoint_json = json.dumps(endpoint)
        json_format = {"Content-Type":"application/json"}
        request_response = requests.request(method='POST', url=self.derms_api.replace('Read','Write'), auth=(self.derms_user,self.derms_password), data=endpoint_json, json=json_format)
        
        if request_response == '200':
            return True
        else:
            return False


## lines below allow this to be run separate from the example file for testing
if __name__ == "__main__":
    test_comms_obj = DERMSComms()
    test_comms_obj.detect_active_connectors()
    test_comms_obj.get_measurements(print_out = True)
    #test_comms_obj.send_evse_power_limit()
    #test_comms_obj.clear_evse_power_limit()


# status is every second
# meter values are 15 seconds
