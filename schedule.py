import os, glob
import numpy as np
from numpy import cos, arccos
from numpy.core.defchararray import add as char_add
import numpy.lib.recfunctions as rec

EARTH_RADIUS = 3958.75 #miles.  this sets the units of all outputs and inputs

def fix_times(times):
    to_decimal_hours =  np.array([1.0, 1/60., 1/3600.])
    b = np.array(np.char.split(times,':').tolist()).astype(float) #inefficient.  but, clean
    decimal_time = (b * to_decimal_hours).sum(axis = -1)
    return decimal_time

def read_gtfs_csv(filename):
    return np.genfromtxt(filename, names = True, delimiter = ',', comments ='%', dtype = None)

def haversine_dist(pos1, pos2, r = 1):
    dtor = np.pi / 180
    pos1 = pos1 * dtor
    pos2 = pos2 * dtor
    cos_lat1 = cos(pos1[..., 0])
    cos_lat2 = cos(pos2[..., 0])
    cos_lat_d = cos(pos1[..., 0] - pos2[..., 0])
    cos_lon_d = cos(pos1[..., 1] - pos2[..., 1])
    return r * arccos(cos_lat_d - cos_lat1 * cos_lat2 * (1 - cos_lon_d))

def join_struct_arrays(arrays):
    """from some dudes on StackOverflow.  add equal length
    structured arrays to produce a single structure with fields
    from both.  input is a sequence of arrays."""
    if False in [len(a) == len(arrays[0]) for a in arrays] :
        raise ValueError ('join_struct_arrays: array lengths do not match.')
    
    newdtype = np.dtype(sum((a.dtype.descr for a in arrays), []))        
    if len(np.unique(newdtype.names)) != len(newdtype.names):
        raise ValueError ('join_struct_arrays: arrays have duplicate fields.')
    newrecarray = np.empty(len(arrays[0]), dtype = newdtype)
    for a in arrays:
        for name in a.dtype.names:
            newrecarray[name] = a[name]
    return newrecarray

def struct_as_dictlist(struct):
    names = struct.dtype.names
    return [dict(zip(names, rec)) for rec in struct]

def nodename(visit):
    try:
        return '{trip_id}_{stop_sequence}'.format(**visit)
    except TypeError:
        return char_add(char_add(visit['trip_id'],'_'), visit['stop_sequence'].astype(str))


class ScheduleAllArray(object):
    """GTFS data in numpy structured arrays."""

    def __init__(self, gtfs_dataset):
        self.distances_between = haversine_dist
        self.visits = self.join_tables(gtfs_dataset, day_of_week = 'Weekday')
        self.transfers_dict = {}

    def join_tables(self, gtfs_dataset, day_of_week = 'Weekday'):
        """Join all GTFS tables into a single table with primary key 'visit_id'.
        Also, add several fields to the visit table: a numeric time and visit_id.
        Slow and memory intensive; sql will be necessary for larger networks"""
        
        stop_fields = ['stop_lat', 'stop_lon', 'stop_name']
        trip_fields = ['route_id', 'trip_headsign']
        self.time_field = 'dtime'
        
        visits = read_gtfs_csv(gtfs_dataset+'/stop_times.txt')
        stops = read_gtfs_csv(gtfs_dataset+'/stops.txt')
        #routes = read_gtfs_csv(gtfs_dataset+'/routes.txt')
        trips = read_gtfs_csv(gtfs_dataset+'/trips.txt')
        
        stop_inds = np.where(stops['stop_id'][:,None] == visits['stop_id'])[0]
        trip_inds = np.where(trips['trip_id'][:,None] == visits['trip_id'])[0]
        stops = stops[stop_inds][stop_fields]
        trips = trips[trip_inds][trip_fields]
        this_dow = np.char.find(visits['trip_id'], day_of_week) >=0 
        visits = rec.append_fields(visits, [self.time_field, 'visit_id'],
                                   [fix_times(visits['departure_time']), nodename(visits)])
        
        return join_struct_arrays([visits[this_dow], stops[this_dow], trips[this_dow]])
               
    def get_trips(self, dow = 'Weekday'):
        thisdow = np.char.find(self.visits['trip_id'], dow) >=0 
        return np.unique(self.visits['trip_id'][thisdow])
    
    def visits_for_trip(self, trip_id):
        """Return a list of dictionaries, where each dictionary is a
        visit in the trip"""
        names = self.visits.dtype.names
        match = self.visits['trip_id'] == trip_id
        return [dict(zip(names, v)) for v in self.visits[match]]

    def visits_between(self, min_time, max_time, at_stops = None):
        """Return a list of dictionaries, where each dictionary is a visit
        with stop times between min_time and max_time to the stops given
        by at_stops"""
        names = self.visits.dtype.names
        close = ( np.any(self.visits['stop_id'][:,None] == at_stops, axis = 1) &
                  (self.visits[self.time_field] > min_time) &
                  (self.visits[self.time_field] < max_time) )
        return [dict(zip(names, v)) for v in self.visits[close]]
        
    def nearby_visits(self, Location, nearby_dict = None,
                      walk_speed = 1.5, max_wait = 20./60.,
                      time_safety = 1/60., dist_threshold = 0.1,
                      **extras):
        """Given a location, determine visits close in both space and time to
        those visits.  Returns a list of dictionaries, where each dictionary is
        a nearby visit"""
        tf = self.time_field
        time_buffer = 1 #hours
        #ignore visits on same route as Location or visits temporally very distant
        prefilter = ( (self.visits['route_id'] != Location['route_id']) &
                      (np.abs(self.visits[tf] - Location[tf]) < time_buffer) )
        if (prefilter.sum() == 0):
            return []
        
        #set up the visit coordinates
        visitlocs = (self.visits[prefilter][['stop_lat','stop_lon']]).view((np.float, 2))
        visitnames = self.visits[prefilter]['visit_id']
        loc = np.vstack([Location['stop_lat'], Location['stop_lon']]).T
        
        #calculate the distance to every (filtered) visit and get spatially acceptable visits
        dist = np.squeeze(self.distances_between(loc[:,None], visitlocs, r = EARTH_RADIUS))
        inds_near = ( (dist < dist_threshold) )
        if (inds_near.sum() == 0):
            return []
        #determine time to walk to the stop, and get visits that are temporally acceptable
        arrival_time = Location[tf] + dist[inds_near]/walk_speed + time_safety
        print(arrival_time.shape)
        delta_time = (self.visits[prefilter][inds_near][tf] -
                      arrival_time)
        close = ((delta_time < max_wait) &
                 (delta_time > 0) )
        print(close.shape, close.sum())
        #combine all filters
        nearby_visits = self.visits[prefilter][inds_near][close]

        return struct_as_dictlist(nearby_visits)
    
    def transfers_from_stop(self, stop_id):
        return self.transfer_dict.get(stop_id, 1)



class ScheduleAllSQL(object):
    """GTFS data in a relational database"""
    pass


class ScheduleSimpleDict(object):
    """Store a simple version of route info: a dictionary of dictionaries
    giving average time between stops, including transfers, as well as a dictionary
    of stop info."""
    def __init__(time_range):
        self.read_arrays()
        self.build_graph(time_range)
        self.distances_between = haversine_dist

    def build_graph(self, time_range):
        in_range = visits[np.where(visits[time_field] > time_range[0] &
                                   visits[time_field] < time_range[1])]
        goodtrips = np.unique(visits[in_range]['trip_id'])
        goodstops = np.unique(visits[in_range]['stop_id'])

    def route_data(self, goodtrips):
        #pick one of the trips for a given route
        for t in goodtrips:
            pass

    def stop_data(self, goodstops):
        self.stop_dict, inds = {},[]
        for s in goodstops:
            ind = np.where(stops['stop_id'] == s)[0]
            self.stop_dict[s] = {'lat':stops[ind]['stop_lat'][0],
                                 'lon':stops[ind]['stop_lon'][0]}
            inds += ind
        self.stop_array = stops[np.array(inds)]
        self.stoplocs = stop_array[['stop_lat','stop_lon']].view((np.float, 2))
        
    def nearest_stops(lat, lon, k_nearest = 5):
        locs = np.array([lat,lon]).T
        dists = self.distances_between(locs[:,None],self.stoplocs)
        n = np.argsort(dists)[:k_nearest+1]
        return self.stop_array[n]['stop_id'].tolist(), dists[n].tolist()
