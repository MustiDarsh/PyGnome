import movers
import numpy as np

from colander import (SchemaNode, Bool, Float, String, Sequence, drop)

from gnome.basic_types import oil_status
from gnome.basic_types import (world_point_type,
                               status_code_type)

from gnome.utilities.projections import FlatEarthProjection

from gnome.environment import GridCurrent
from gnome.environment.gridded_objects_base import Grid_U, VectorVariableSchema

from gnome.persist.base_schema import ObjTypeSchema
from gnome.persist.validators import convertible_to_seconds
from gnome.persist.extend_colander import LocalDateTime, FilenameSchema
from gnome.persist.base_schema import GeneralGnomeObjectSchema
from __builtin__ import property



class PyCurrentMoverSchema(ObjTypeSchema):
    current = GeneralGnomeObjectSchema(
        acceptable_schemas=[VectorVariableSchema, GridCurrent._schema],
        save=True, update=True, save_reference=True
    )
    filename = FilenameSchema(
        missing=drop, save=True, update=False, isdatafile=True
    )
    current_scale = SchemaNode(
        Float(), missing=drop, save=True, update=True
    )
    extrapolation_is_allowed = SchemaNode(
        Bool(), missing=drop, save=True, update=True
    )
#    time_offset = SchemaNode(
#        Float(), missing=drop, save=True, update=True
#    )
    on = SchemaNode(
        Bool(), missing=drop, save=True, update=True
    )
    active_start = SchemaNode(
        LocalDateTime(), missing=drop,
        validator=convertible_to_seconds,
        save=True, update=True
    )
    active_stop = SchemaNode(
        LocalDateTime(), missing=drop,
        validator=convertible_to_seconds,
        save=True, update=True
    )
    data_start = SchemaNode(
        LocalDateTime(), validator=convertible_to_seconds, read_only=True
    )
    data_stop = SchemaNode(
        LocalDateTime(), validator=convertible_to_seconds, read_only=True
    )


class PyCurrentMover(movers.PyMover):

    _schema = PyCurrentMoverSchema

    _ref_as = 'py_current_movers'

    _req_refs = {'current': GridCurrent}

    def __init__(self,
                 filename=None,
                 current=None,
                 time_offset=0,
                 current_scale=1,
                 uncertain_duration=24 * 3600,
                 uncertain_time_delay=0,
                 uncertain_along=.5,
                 uncertain_across=.25,
                 uncertain_cross=.25,
                 default_num_method='RK2',
                 extrapolation_is_allowed=False,
                 **kwargs
                 ):
        """
        Initialize a PyCurrentMover

        :param filename: absolute or relative path to the data file(s):
                         could be a string or list of strings in the
                         case of a multi-file dataset
        :param current: Environment object representing currents to be
                        used. If this is not specified, a GridCurrent object
                        will attempt to be instantiated from the file
        :param active_start: datetime when the mover should be active
        :param active_stop: datetime after which the mover should be inactive
        :param current_scale: Value to scale current data
        :param uncertain_duration: how often does a given uncertain element
                                   get reset
        :param uncertain_time_delay: when does the uncertainly kick in.
        :param uncertain_cross: Scale for uncertainty perpendicular to the flow
        :param uncertain_along: Scale for uncertainty parallel to the flow
        :param time_offset: Time zone shift if data is in GMT
        :param num_method: Numerical method for calculating movement delta.
                           Choices:('Euler', 'RK2', 'RK4')
                           Default: RK2
        """
        self.filename = filename
        self.current = current

        if self.current is None:
            if filename is None:
                raise ValueError("must provide a filename or current object")
            else:
                self.current = GridCurrent.from_netCDF(filename=self.filename,
                                                       **kwargs)

        self.extrapolation_is_allowed = extrapolation_is_allowed
        self.current_scale = current_scale

        self.uncertain_along = uncertain_along
        self.uncertain_across = uncertain_across
        self.uncertain_duration = uncertain_duration
        self.uncertain_time_delay = uncertain_time_delay

        self.model_time = 0

        self.positions = np.zeros((0, 3), dtype=world_point_type)
        self.delta = np.zeros((0, 3), dtype=world_point_type)
        self.status_codes = np.zeros((0, 1), dtype=status_code_type)

        # either a 1, or 2 depending on whether spill is certain or not
        self.spill_type = 0
        (super(PyCurrentMover, self)
         .__init__(default_num_method=default_num_method, **kwargs))


    @classmethod
    def from_netCDF(cls,
                    filename=None,
                    name=None,
                    time_offset=0,
                    current_scale=1,
                    uncertain_duration=24 * 3600,
                    uncertain_time_delay=0,
                    uncertain_along=.5,
                    uncertain_across=.25,
                    uncertain_cross=.25,
                    **kwargs):
        """
        Function for specifically creating a PyCurrentMover from a file
        """
        current = GridCurrent.from_netCDF(filename, **kwargs)

        return cls(name=name,
                   current=current,
                   filename=filename,
                   time_offset=time_offset,
                   current_scale=current_scale,
                   uncertain_along=uncertain_along,
                   uncertain_across=uncertain_across,
                   uncertain_cross=uncertain_cross,
                   **kwargs)

    @property
    def filename(self):
        if hasattr(self, '_filename'):
            if self._filename is None and self.current is not None:
                return self.current.data_file
            else:
                return self._filename
        else:
            return None

    @filename.setter
    def filename(self, fn):
        self._filename = fn

    @property
    def data_start(self):
        return self.current.data_start

    @property
    def data_stop(self):
        return self.current.data_stop

    @property
    def is_data_on_cells(self):
        return self.current.grid.infer_location(self.current.u.data) != 'node'

    def get_grid_data(self):
        """
            The main function for getting grid data from the mover
        """
        if isinstance(self.current.grid, Grid_U):
            return self.current.grid.nodes[self.current.grid.faces[:]]
        else:
            lons = self.current.grid.node_lon
            lats = self.current.grid.node_lat

            return np.column_stack((lons.reshape(-1), lats.reshape(-1)))

    def get_center_points(self):
        if (hasattr(self.current.grid, 'center_lon') and
                self.current.grid.center_lon is not None):
            lons = self.current.grid.center_lon
            lats = self.current.grid.center_lat

            return np.column_stack((lons.reshape(-1), lats.reshape(-1)))
        else:
            lons = self.current.grid.node_lon
            lats = self.current.grid.node_lat

            if len(lons.shape) == 1:
                # we are ugrid
                triangles = self.current.grid.nodes[self.current.grid.faces[:]]
                centroids = np.zeros((self.current.grid.faces.shape[0], 2))
                centroids[:, 0] = np.sum(triangles[:, :, 0], axis=1) / 3
                centroids[:, 1] = np.sum(triangles[:, :, 1], axis=1) / 3

            else:
                c_lons = (lons[0:-1, :] + lons[1:, :]) / 2
                c_lats = (lats[:, 0:-1] + lats[:, 1:]) / 2
                centroids = np.column_stack((c_lons.reshape(-1),
                                             c_lats.reshape(-1)))

            return centroids

    def get_scaled_velocities(self, time):
        """
        :param model_time=0:
        """
        current = self.current
        lons = current.grid.node_lon
        lats = current.grid.node_lat

        # GridCurrent.at needs Nx3 points [lon, lat, z] and a time T
        points = np.column_stack((lons.reshape(-1),
                                  lats.reshape(-1),
                                  np.zeros_like(current.grid.node_lon
                                                .reshape(-1))
                                  ))
        vels = current.at(points, time)

        return vels

    def get_move(self, sc, time_step, model_time_datetime, num_method=None):
        """
        Compute the move in (long,lat,z) space. It returns the delta move
        for each element of the spill as a numpy array of size
        (number_elements X 3) and dtype = gnome.basic_types.world_point_type

        Base class returns an array of numpy.nan for delta to indicate the
        get_move is not implemented yet.

        Each class derived from Mover object must implement it's own get_move

        :param sc: an instance of gnome.spill_container.SpillContainer class
        :param time_step: time step in seconds
        :param model_time_datetime: current model time as datetime object

        All movers must implement get_move() since that's what the model calls
        """
        positions = sc['positions']

        if self.active and len(positions) > 0:
            status = sc['status_codes'] != oil_status.in_water
            pos = positions[:]

            res = self.delta_method(num_method)(sc, time_step,
                                                model_time_datetime,
                                                pos,
                                                self.current)

            if res.shape[1] == 2:
                deltas = np.zeros_like(positions)
                deltas[:, 0:2] = res
            else:
                deltas = res

            deltas = FlatEarthProjection.meters_to_lonlat(deltas, positions)
            deltas[status] = (0, 0, 0)
        else:
            deltas = np.zeros_like(positions)

        return deltas
