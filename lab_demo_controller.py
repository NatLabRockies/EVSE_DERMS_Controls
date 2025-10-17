import os 
from os.path import normpath, join
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time

class EV:
    def __init__(self, ev_id, plug_in_time, duration=12*60, priority_factor=1, SOC=50, max_power=9.6, battery_size=90, min_power=0.0):
        self.ev_id = ev_id
        self.plug_in_time = plug_in_time
        self.duration = duration
        self.priority_factor = priority_factor
        self.allocated_power = 0.0
        self.SOC = SOC
        self.max_power = max_power
        self.min_power = min_power
        self.battery_size = battery_size # in kWh

    def is_connected(self, current_time):
        return self.plug_in_time <= current_time < (self.plug_in_time + timedelta(minutes=self.duration))

class ChargingStation:
    def __init__(self):
        self.connected_evs = []

    def add_ev(self, ev):
        self.connected_evs.append(ev)

    def remove_ev(self, ev_name):
        for ev in self.connected_evs:
            if ev.ev_id == ev_name:
                self.connected_evs.remove(ev)
                print(f'line 31 removing {ev.ev_id}')
        print(f'new management system list: {self.connected_evs}')


class ChargingManagementSystem:
    def __init__(self, 
                 capacity_series, 
                 allocation_method='first_come_first_served',
                 ess_size=13.5,             #stationary storage in kWh
                 max_power_ess=11.5,        #in kW (charging ess is positive)
                 min_power_ess=-11.5,       #in kW (discharging ess is negative)
                 max_power_l2=9.7,          #in kW
                 min_power_l2=3.3):         #in kW
        self.station = ChargingStation()
        self.current_time = None
        self.capacity_series = capacity_series
        self.available_capacity_series = pd.Series(dtype=float, index=capacity_series.index)
        self.ev_power_series = pd.DataFrame(index=capacity_series.index)
        self.allocation_method = allocation_method

    def update_time(self, new_time):
        self.current_time = new_time

    def add_ev(self, ev):
        self.station.add_ev(ev)
        self.ev_power_series[ev.ev_id] = 0.0  # Initialize EV power series with zeros

    def remove_ev(self, ev_name):
        self.station.remove_ev(ev_name)
        self.ev_power_series = self.ev_power_series.drop([ev_name.lower()], axis=1) # remove from management system, this deletes historical data at the CMS#reset to 0 power
    
    def update_soc(self, ev_name, soc):
        i_ev = 0
        for ev in self.station.connected_evs:
            if ev.ev_id == ev_name:
                self.station.connected_evs[i_ev].SOC = soc
                break
            i_ev += 1

    def update_priority(self, ev_name, pf):
        i_ev = 0
        for ev in self.station.connected_evs:
            if ev.ev_id == ev_name:
                self.station.connected_evs[i_ev].priority_factor = pf
                break
            i_ev += 1

    def allocate_power_first_come_first_served(self):
        remaining_capacity = self.capacity_series[self.capacity_series.index <= self.current_time].iloc[-1]
        sorted_evs = sorted(self.station.connected_evs, key=lambda ev: ev.plug_in_time)
        
        for ev in sorted_evs:
            if ev.is_connected(self.current_time):
                if remaining_capacity > 0:
                    allocatable_power = min(remaining_capacity, ev.max_power)
                    ev.allocated_power = allocatable_power
                    remaining_capacity -= ev.allocated_power
                else:
                    ev.allocated_power = 0.0
    def allocate_power_equal_sharing(self):
            remaining_capacity = self.capacity_series[self.capacity_series.index <= self.current_time].iloc[-1]
            connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]
            if connected_evs:
                equal_power = remaining_capacity / len(connected_evs)
                residual_power = 0.0
                evs_maxed_out = []
                for ev in connected_evs:
                    ev.allocated_power = min(equal_power, ev.max_power)
                    residual_power_ev = equal_power - ev.allocated_power
                    if residual_power_ev > 0:
                        residual_power = residual_power + residual_power_ev
                        evs_maxed_out.append(ev.ev_id)
                # check for residual power if one ev cannot take it's full share
                if residual_power > 0:
                    bonus_power = residual_power / (len(connected_evs)-len(evs_maxed_out))
                    for ev in connected_evs:
                        if not ev.ev_id in evs_maxed_out:
                            ev.allocated_power = min(ev.allocated_power + bonus_power, ev.max_power)

    def allocate_power_based_on_soc(self):
        connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]
        if connected_evs:
            remaining_capacity = self.capacity_series[self.capacity_series.index <= self.current_time].iloc[-1]
            total_capacity = self.capacity_series[self.capacity_series.index <= self.current_time].iloc[-1]
            total_inverse_soc = sum(1 - ev.SOC/100 for ev in connected_evs)
            
            # First round allocation based on SOC
            for ev in connected_evs:
                proportion = (1 - ev.SOC/100) / total_inverse_soc

                allocatable_power = min(proportion * total_capacity, ev.max_power)
                ev.allocated_power = allocatable_power
                remaining_capacity -= ev.allocated_power
            
            # Second round allocation based on remaining capacity
            # If there's remaining capacity, distribute it again proportionally for all EV has allocated power less than 9.6 KW
            # Filter out EVs that already have less than 9.6 kW allocated
            evs_under_max_power = [ev for ev in connected_evs if ev.allocated_power < ev.max_power]
            if evs_under_max_power:
                total_inverse_soc_under_max = sum(1 - ev.SOC/100 for ev in evs_under_max_power)

                # Distribute the remaining capacity proportionally among EVs with less than 9.6 kW
                for ev in evs_under_max_power:
                    proportion = (1 - ev.SOC/100) / total_inverse_soc_under_max
                    additional_power = min(proportion * remaining_capacity, ev.max_power - ev.allocated_power)
                    ev.allocated_power += additional_power
                    remaining_capacity -= additional_power

    def allocate_power_priority_factors(self):
        connected_evs = [ev for ev in self.station.connected_evs if ev.is_connected(self.current_time)]
        total_priority = sum(ev.priority_factor for ev in connected_evs)
        remaining_capacity = self.capacity_series[self.capacity_series.index <= self.current_time].iloc[-1]
        for ev in connected_evs:
            allocatable_power = min((ev.priority_factor / total_priority) * remaining_capacity, ev.max_power)
            ev.allocated_power = allocatable_power


    def simulate(self, start_time, end_time, time_step=timedelta(minutes=1)):

        self.current_time = start_time
        
        if self.current_time is not None:
            while self.current_time <= end_time:
                self.update_time(self.current_time)
                if self.allocation_method == 'first_come_first_served':
                    self.allocate_power_first_come_first_served()
                elif self.allocation_method == 'equal_sharing':
                    self.allocate_power_equal_sharing()
                elif self.allocation_method == 'soc_priority':
                    self.allocate_power_based_on_soc()
                elif self.allocation_method == 'priority_factors':
                    self.allocate_power_priority_factors()
                
                # get the previous closest to the current time:
                ev_power_series_timei = 0
                for t in self.ev_power_series.index:
                    if t <= self.current_time:
                        ev_power_series_timei = t

                for ev in self.station.connected_evs:
                    print(f'ev: {ev.ev_id} power set to {ev.allocated_power} in series {self.ev_power_series.at[ev_power_series_timei, ev.ev_id]}')
                    self.ev_power_series.at[ev_power_series_timei, ev.ev_id] = ev.allocated_power# if ev.is_connected(self.current_time) else 0
                
                self.current_time += time_step


    def update_timestep_control(self, plugin=[], unplug=[], time_now=datetime(2024, 6, 25, 9, 5), soc_update=[], timestep=timedelta(seconds=5), priority_factors=[]):
        # update it at each timestep
        # if you get a plugin signal add an ev
        for evse in plugin:
            evse = evse.lower()
            if evse == 'veefil':
                max_power = 15
            elif evse.startswith('pulsar'):
                max_power = 11.5
            else:
                max_power = 9.6
            evse_i = EV(ev_id=evse, plug_in_time=time_now, max_power=max_power) # SOC=soc_update[i]
            self.add_ev(evse_i)
        # if you get an unplug signal remove that ev
        for evse_name in unplug:
            self.remove_ev(evse_name)
        # update_soc reading
        for ev_id, soc_i in soc_update:
            print(f'soc read for {ev_id} is: {soc_i}')
            if soc_i: # Nones do not get updates
                self.update_soc(ev_id, soc_i)
        for ev_id, priority_factor in priority_factors:
            print(f'priority factor for {ev_id} is: {priority_factor}')
            if priority_factor:
                self.update_priority(ev_id, priority_factor)
        # update power allocation
        self.simulate(time_now, end_time=time_now+timestep)
        
        return self.ev_power_series


if __name__ == "__main__":
    # below is a test of the algorithm without sending or recieving messages from DERMS
    timestep = timedelta(minutes=5)
    time_index = pd.date_range(start=(datetime.now()).strftime('%D %H:00:00'), end=(datetime.now()+timedelta(hours=1)).strftime('%D %H:00:00'), freq=timestep)
    
    capacity_series = pd.Series([15.0 for i in time_index], index=time_index)
    management_system = ChargingManagementSystem(capacity_series, allocation_method='first_come_first_served')
    power_series = management_system.update_timestep_control(plugin=['evse1'], soc_update=[('evse2',10)], priority_factors=[('evse2', 2)], time_now=datetime.now())
    time.sleep(10)
    power_series = management_system.update_timestep_control(plugin=['evse1'], time_now=datetime.now())
    print(f'power series: {power_series}')
    print(power_series.to_string())


