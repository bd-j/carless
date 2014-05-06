import schedule
import transit_graph as tgraph
#import walkers

rp = {'transit_dataset': '/Users/bjohnson/Projects/carless/data/santa_cruz'}

data = schedule.ScheduleAllArray(rp['transit_dataset'])
graph = tgraph.TransitGraphNX()
#graph.transfer_pars['max_wait'] = 20/60.
graph.add_trips_to_graph(data = data)

#journeys = walkers.Locations
