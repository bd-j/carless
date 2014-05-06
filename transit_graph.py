#Classes and methods for building and storing a graph based on
#GTFS data

import numpy as np
from operator import itemgetter
from numpy.core.defchararray import add as char_add
import networkx as nx

class TransitGraph(object):
            
    def add_trips_to_graph(self, data = None):
        if data is None:
            data = self.data
        tripidlist = data.get_trips()
        print('{0} trips'.format(len(tripidlist)))
        for i,tid in enumerate(tripidlist):
            visitlist = data.visits_for_trip(tid)
            print('adding trip {0}: {1} on route {2}'.format(i, tid, visitlist[0]['route_id']))
            self.add_one_trip(visitlist, data = data)


class TransitGraphNX(nx.DiGraph, TransitGraph):
    """Build graph using networkx."""

    transfer_pars = {'walk_speed': 1.5, 'dist_threshold': 0.05,
                     'max_wait':10/60., 'time_safety': 3/60.}

    def add_one_trip(self, trip, data = None, **extras):
        """start adding nodes and edges to the graph, using visits along a particular
        trip. visits should be a list of dicts, with each dict being a particular
        visit (stop_times)"""
        
        if data is None:
            data = self.data
            
        tf = data.time_field
        trip.sort(key = itemgetter('stop_sequence'))
        for i, v in enumerate(trip):
            self.add_node(v['visit_id'], v)
            try:
                travel_time = trip[i+1][tf] - v[tf]
                self.add_edge(v['visit_id'], trip[i+1]['visit_id'],
                              weight = travel_time, edgetype = 'ride')
            except IndexError:
                pass #end of the line, so no edges
            #transfers = data.transfers_from_stop(v['stop_id'])
            transfers = True
            if transfers:
                #print('transfer from {0}'.format(n1))
                elist = self.transfer_edges(v, data = data,
                                            #nearby_dict = transfers,
                                            **self.transfer_pars)
                if elist:
                    self.add_edges_from(elist)

    def transfer_edges(self, v, data = None, **extras):
        """find visits close in time to the given visit v for each of the spatially
        close stops. v is a dict describing the initial visit, while transfer_stops is a
        list of stops that are spatially close to v.  create a list of edge_tuples and
        add them to the graph."""
        if data is None:
            data = self.data
        tf = data.time_field
        close_visits = data.nearby_visits(v, **extras)
        if len(close_visits) == 0:
            return None
        return [(v['visit_id'], cv['visit_id'], {'weight':cv[tf] - v[tf], 'edgetype': 'transfer'})
                for cv in close_visits]
        
class TransitGraphFuzzy(object):
    """Use simple dictionary to return approximate travel times.  A method is provided
    to recursively search for the shortest path from any given stop to all other stops."""

    def __init__(data):
        self.edges = data.edges
        self.stops = data.stop_dict
        
    def path_length(self, source, lengths, max_time = 1e10):
        """recursuvely explore the graph from source, adding path lengths if they are shorter
        than any previously found path and the optional max length"""
        for d in self.edges[source].keys():
            step = length[source] + self.edges[source][d]
            if (step < max_time) & (step < length.get(d, 0)):
                length[d] = step
                self.path_length(d, lengths, max_time = max_time) 

    def add_source(self, data, Location = {'lat':32., 'lon':-122.}):
        """add a source location to the route graph"""
        stops, dists = data.nearest_stops(Location['lat'], Location['lon'], k_nearest = 5)
        #stops and dists are 1-d arrays
        self.stops['start'] = Location
        self.edges['start'] = {}
        for s, d in zip(stops, dists):
            self.edges[s]['start'] = d/self.walk_speed
            self.edges['start'][s] = d/self.walk_speed

    def length_to_stops(self):
        lengths = {'start':0.}
        self.path_length('start', lengths, max_time = self.max_time)
        return lengths

    def set_location(self, Location):
        self.Location = Location
        self.add_source(self.Location)
        self.lengths = self.length_to_stops(self.Location)

    def length_to_positions(self, positions):
        """calculate path length to an array of positions"""
        stops, dists = data.nearest_stops_multi(positions)
        #stops, dists are a 1-d array and an n_locations x nstops array
        lengths = np.map
        dists = dists/self.walk_speed + np.array([self.lengths[s['stop_id']] for s in stops])[:,None]
        return dists.min(axis = -1)

    def plot_transit_time(Location, positions, grid = False):
        self.set_location(Location)
        d = length_to_positions(positions)
        pl.scatter(positions['lon'],positions['lat'], c = d)
        if grid:
            pl.imshow(d, interpolation = 'nearest')
            
class TransitGraphGT(TransitGraph):
    """Build graph using graph_tool"""
    pass
