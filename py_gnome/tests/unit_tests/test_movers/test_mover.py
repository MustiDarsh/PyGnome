'''
Test some of the base class functionality independent of derived classes.
Just simpler to do the testing here
Tests the Process methods and the Mover's get_move
'''
from datetime import datetime, timedelta

import numpy as np

from pytest import raises
from ..conftest import sample_sc_release

from gnome.utilities.inf_datetime import InfDateTime
from gnome.movers import Mover


def test_exceptions():
    with raises(ValueError):
        now = datetime.now()
        _mover = Mover(active_start=now, active_stop=now)


def test_default_properties():
    mover = Mover()

    assert mover.name == 'Mover'
    assert mover.on is True

    assert mover.active_start == InfDateTime('-inf')
    assert mover.active_stop == InfDateTime('inf')

    assert mover.array_types == set()
    assert mover.make_default_refs is True


class TestActive:
    time_step = 15 * 60  # seconds
    model_time = datetime(2012, 8, 20, 13)
    sc = sample_sc_release(1, (0, 0, 0))  # no used for anything
    mv = Mover()

    def test_active_default(self):
        mv = Mover()
        mv.prepare_for_model_step(self.sc, self.time_step, self.model_time)

        assert mv.active is True  # model_time = active_start

    def test_active_start_modeltime(self):
        mv = Mover(active_start=self.model_time)
        mv.prepare_for_model_step(self.sc, self.time_step, self.model_time)

        assert mv.active is True  # model_time = active_start

    def test_active_start_after_one_timestep(self):
        start_time = self.model_time + timedelta(seconds=self.time_step)

        mv = Mover(active_start=start_time)
        mv.prepare_for_model_step(self.sc, self.time_step, self.model_time)

        assert mv.active is False  # model_time + time_step = active_start

    def test_active_start_after_half_timestep(self):
        self.mv.active_start = \
            self.model_time + timedelta(seconds=self.time_step / 2)
        self.mv.prepare_for_model_step(self.sc, self.time_step,
                                       self.model_time)

        # model_time + time_step / 2 = active_start
        assert self.mv.active is True

    # Next test just some more borderline cases that active is set correctly
    def test_active_stop_greater_than_timestep(self):
        self.mv.active_start = self.model_time
        self.mv.active_stop = (self.model_time +
                               timedelta(seconds=1.5 * self.time_step))
        self.mv.prepare_for_model_step(self.sc, self.time_step,
                                       self.model_time)

        # model_time + 1.5 * time_step = active_stop
        assert self.mv.active is True

    def test_active_stop_after_half_timestep(self):
        self.mv.active_start = self.model_time
        self.mv.active_stop = (self.model_time +
                               timedelta(seconds=0.5 * self.time_step))
        self.mv.prepare_for_model_step(self.sc, self.time_step,
                                       self.model_time)

        # model_time + 1.5 * time_step = active_stop
        assert self.mv.active is True

    def test_active_stop_less_than_half_timestep(self):
        self.mv.active_start = self.model_time
        self.mv.active_stop = (self.model_time +
                               timedelta(seconds=0.25 * self.time_step))
        self.mv.prepare_for_model_step(self.sc, self.time_step,
                                       self.model_time)

        # current_model_time = active_stop
        assert self.mv.active is False


def test_get_move():
    '''
    assert base class get_move returns an array of nan[s]
    '''
    time_step = 15 * 60  # seconds
    model_time = datetime(2012, 8, 20, 13)
    sc = sample_sc_release(10, (0, 0, 0))  # no used for anything

    mv = Mover()
    delta = mv.get_move(sc, time_step, model_time)

    assert np.all(np.isnan(delta))
