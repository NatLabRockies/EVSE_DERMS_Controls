import requests
from datetime import datetime, timedelta
import json

derms_url = 'http://127.0.0.1:5555/json/reply' # replace with your derms api url
username = 'my_username' # replace with the username for the scm on your derms
password = 'my_password' # replace with the username for the scm on your derms

# OCPP 1.6J format: MessageTypeId, UniqueId
# the string below is a json formatted in OCPP1.6J with escapes such that the " " get added and sent via the API properly
# several of the values are standard for EVSE profile limits including the 2 defining the message type. The stackLevel is the priority. Duration is given in seconds
# the API call sends the profile string value as the endpoint string value
evseid = 'EVSE0'
connector = 1
profile_str_value = "[2,\"123\",\"SetChargingProfile\",{\"connectorId\":"+str(connector)+",\"csChargingProfiles\":{\"chargingProfileId\":123,\"stackLevel\":1,\"chargingProfilePurpose\":\"TxProfile\",\"chargingProfileKind\":\"Absolute\",\"recurrencyKind\":\"Daily\",\"validFrom\":\""+datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')+"\",\"validTo\":\""+ (datetime.now()+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')+"\",\"chargingSchedule\":{\"duration\":86400,\"startSchedule\":\""+datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')+"\",\"chargingRateUnit\":\"A\",\"chargingSchedulePeriod\":[{\"startPeriod\":0,\"limit\":5.432}, {\"startPeriod\":60,\"limit\":1.2345}],\"minChargingRate\":8.0}}}]"
endpoint = {"Name":f"ANM.OCPP.{evseid}.SetChargingProfile",
        "StringValue":profile_str_value}
# uncomment the next line to clear any charging profile sent previously
#endpoint = {"Name":f"ANM.OCPP.{evseid}.ClearChargingProfile",
#        "StringValue":"[2,\"123\", \"ClearChargingProfile\", {\"connectorId\":"+str(connector)+"}]"}
endpoint_json = json.dumps(endpoint)
json_format = {"Content-Type":"application/json"}
response = requests.request(method='POST', url=derms_url, auth=(username, password), data = endpoint_json, json=json_format)

print(response) # a successful api call will return 200 or "Success"

response_json = response.json() # the response json will contain the actual information
print(response_json)


