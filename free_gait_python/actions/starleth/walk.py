#! /usr/bin/env python

# Action that generates footholds based on the current desired
# velocities.

import tf
from tf.transformations import *
from numpy import *
from copy import deepcopy
from collections import *

class Leg:
    LF = 0
    RF = 1
    LH = 2
    RH = 3
    
    @staticmethod
    def to_text(leg):
        if leg == Leg.LF:
            return 'leftFore'
        elif leg == Leg.RF:
            return 'rightFore'
        elif leg == Leg.LH:
            return 'leftHind'
        elif leg == Leg.RH:
            return 'rightHind'
        else:
            return None

class Direction:
    FORWARD = 0
    BACKWARD = 1
    LEFT = 2
    RIGHT = 3
           
class Action(ActionBase):

    def __init__(self, client):
            
        ActionBase.__init__(self, client)
        self.trigger = TriggerOnFeedback(1, 0.5)
        self.timeout = rospy.Duration(10)
        self.keep_alive = True
        
        self.velocity = array([1, 0]) # TODO
        self.direction = None
        self.leg = None
        self.footprint = None
        self.next_footprint = None
        
        self.velocity_factor = array([0.3, 0.05])
        self.first_side_factor = 0.5
        self.default_foot_position = dict()
        self.default_foot_position[Leg.LF]  = array([ 0.3,  0.2])
        self.default_foot_position[Leg.RF] = array([ 0.3, -0.2])
        self.default_foot_position[Leg.LH]  = array([-0.3,  0.2])
        self.default_foot_position[Leg.RH] = array([-0.3, -0.2])
        self.velocity_frame = "footprint"
        self.step_frame = "map"
        
        self.gait_pattern = dict()
        self.gait_pattern[Direction.FORWARD] = [Leg.RH, Leg.RF, Leg.LH, Leg.LF]
        self.gait_pattern[Direction.BACKWARD] = deepcopy(self.gait_pattern[Direction.FORWARD])
        self.gait_pattern[Direction.BACKWARD].reverse()
        self.gait_pattern[Direction.RIGHT] = [Leg.LH, Leg.RH, Leg.LF, Leg.RF]
        self.gait_pattern[Direction.LEFT] = deepcopy(self.gait_pattern[Direction.RIGHT])
        self.gait_pattern[Direction.LEFT].reverse()
        
        self.tf_listener = tf.TransformListener()
        rospy.sleep(1.0) # fix for tf bug
        
        self._generate_goal()

    def _active_callback(self):
        # Immediate return because action runs in background.
        self.state = ActionState.DONE
        self.result = free_gait_msgs.msg.StepResult()
        self.result.status = self.result.RESULT_UNKNOWN
        
    def _feedback_callback(self, feedback):
        ActionBase._feedback_callback(self, feedback)
        if self.trigger.check(self.feedback):
            self._generate_goal()
            self.send_goal()
            
    def _done_callback(self, status, result):
        pass
            
    def wait_for_result(self):
        wait_for_done = WaitForDone(self)
        wait_for_done.wait();

    def _generate_goal(self):
        direction_change = self._update_direction()
        if self.direction is None:
            # Stop walking.
            self.leg = None
            self.footprint = None
        elif direction_change:
            # Change of direction.
            self._initialize_footprint()
            self.leg = None
            
        self._select_leg()
        foothold = self._compute_foothold()
        
        self.goal = free_gait_msgs.msg.StepGoal()
        step = free_gait_msgs.msg.Step()
        step.step_number = 1
        swing_data = free_gait_msgs.msg.SwingData()
        swing_data.name = Leg.to_text(self.leg);
        swing_data.profile.target.header.frame_id = self.step_frame
        swing_data.profile.target.point = geometry_msgs.msg.Point(foothold[0], foothold[1], foothold[2])
        swing_data.profile.duration = rospy.Duration(0.8)
        step.swing_data.append(swing_data)
        base_shift_data = free_gait_msgs.msg.BaseShiftData()
        base_shift_data.name = 'pre_step'
        base_shift_data.profile.duration = self._get_base_shift_duration()
        step.base_shift_data.append(base_shift_data)
        self.goal.steps.append(step)
        
    def _initialize_footprint(self):
        self.footprint = get_transform(self.step_frame, self.velocity_frame, listener = self.tf_listener)
        self.next_footprint = None
        
    def _update_direction(self):
        if all(self.velocity == 0):
            new_direction = None
        if abs(self.velocity[0]) >= abs(self.velocity[1]):
            if self.velocity[0] >= 0:
                new_direction = Direction.FORWARD
            else:
                new_direction = Direction.BACKWARD
        else:
            if self.velocity[1] >= 0:
                new_direction = Direction.LEFT
            else:
                new_direction = Direction.RIGHT

        direction_change = False
        if new_direction != self.direction:
            direction_change = True
        self.direction = new_direction
        return direction_change

    def _select_leg(self):
        if self.direction is None:
            self.leg = None
            return
        if self.leg is None:
            self.leg = self.gait_pattern[self.direction][0]
            return
        index = self.gait_pattern[self.direction].index(self.leg)
        index = index + 1
        if index >= len(self.gait_pattern[self.direction]):
            index = 0
            self.footprint = self.next_footprint
        self.leg = self.gait_pattern[self.direction][index]
                
    def _compute_foothold(self):
        if self.gait_pattern[self.direction].index(self.leg) < 2:
            side_factor = self.first_side_factor
        else:
            side_factor = 1
            
        footprint_shift = translation_matrix(append(side_factor * self.velocity_factor * self.velocity, 0))
        #footprint_rotation = #TODO def rotation_matrix(angle, direction, point=None):
        self.next_footprint = concatenate_matrices(self.footprint, footprint_shift)

        position_in_footprint = append(self.default_foot_position[self.leg], [0, 1])
        
        position = (self.next_footprint.dot(position_in_footprint))[:3]
        return position
    
    def _get_base_shift_duration(self):
        # Pre step base shift duration.
        index = self.gait_pattern[self.direction].index(self.leg)
        if index == 1 or index == 3:
            return rospy.Duration(0.3)
        else:
            return rospy.Duration(0.8)

action = Action(action_loader.client)
