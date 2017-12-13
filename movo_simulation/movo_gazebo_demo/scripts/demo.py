#!/usr/bin/env python

# Copyright (c) 2015, Fetch Robotics Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the Fetch Robotics Inc. nor the names of its
#       contributors may be used to endorse or promote products derived from
#       this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL FETCH ROBOTICS INC. BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Author: Michael Ferguson

import copy
import actionlib
import rospy
import sys
import tf

from moveit_msgs.msg import Constraints, OrientationConstraint

from moveit_python import (MoveGroupInterface,
                           PlanningSceneInterface,
                           PickPlaceInterface)
from moveit_python.geometry import rotate_pose_msg_by_euler_angles

from movo_action_clients.gripper_action_client import GripperActionClient
from movo_action_clients.move_base_action_client import MoveBaseActionClient
from movo_action_clients.torso_action_client import TorsoActionClient

from control_msgs.msg import PointHeadAction, PointHeadGoal
from grasp_msgs.msg import FindGraspableObjectsAction, FindGraspableObjectsGoal
from shape_msgs.msg import SolidPrimitive as sp
from geometry_msgs.msg import Pose2D,PoseStamped
from moveit_msgs.msg import PlaceLocation, MoveItErrorCodes

# Point the head using controller
class PointHeadClient(object):

    def __init__(self):
        
        
        self.client = actionlib.SimpleActionClient("movo/head_controller/point_head_action", PointHeadAction)
        rospy.loginfo("Waiting for head_controller...")
        self.client.wait_for_server()
        self.pag = PointHeadGoal()
        self.pag.max_velocity = 1.0
        self.pag.pointing_axis.x = 1.0
        self.pag.pointing_frame = "/kinect2_link"

    def look_at(self, x, y, z, frame, duration=1.0):
        self.pag.target.header.stamp = rospy.get_rostime()
        self.pag.target.header.frame_id = frame
        self.pag.target.point.x = x
        self.pag.target.point.y = y
        self.pag.target.point.z = z
        self.pag.min_duration = rospy.Duration(duration)
        self.client.send_goal(self.pag)
        self.client.wait_for_result()

# Tools for grasping
class GraspingClient(object):

    def __init__(self,sim=False):
        self.scene = PlanningSceneInterface("base_link")
        self.move_group = MoveGroupInterface("upper_body","base_link")
        self.lmove_group = MoveGroupInterface("left_arm","base_link")
        self.rmove_group = MoveGroupInterface("right_arm","base_link")
        self.move_group.setPlannerId("RRTConnectkConfigDefault")
        self.lmove_group.setPlannerId("RRTConnectkConfigDefault")
        self.rmove_group.setPlannerId("RRTConnectkConfigDefault")
        self._upper_body_joints = ["right_elbow_joint",
                        "right_shoulder_lift_joint",
                        "right_shoulder_pan_joint",
                        "right_wrist_1_joint",
                        "right_wrist_2_joint",
                        "right_wrist_3_joint",
                        "left_elbow_joint",
                        "left_shoulder_lift_joint",
                        "left_shoulder_pan_joint",
                        "left_wrist_1_joint",
                        "left_wrist_2_joint",
                        "left_wrist_3_joint",
                        "linear_joint",
                        "pan_joint",
                        "tilt_joint"]
        self._right_arm_joints = ["right_elbow_joint",
                        "right_shoulder_lift_joint",
                        "right_shoulder_pan_joint",
                        "right_wrist_1_joint",
                        "right_wrist_2_joint",
                        "right_wrist_3_joint"]
        self._left_arm_joints = ["left_elbow_joint",
                        "left_shoulder_lift_joint",
                        "left_shoulder_pan_joint",
                        "left_wrist_1_joint",
                        "left_wrist_2_joint",
                        "left_wrist_3_joint"]
        
        self.pickplace = [None]*2
        self.pickplace[0] = PickPlaceInterface("left_arm", "left_gripper", verbose=True)
        self.pickplace[0].planner_id = "RRTConnectkConfigDefault"
        self.pickplace[1] = PickPlaceInterface("right_arm", "right_gripper", verbose=True)
        self.pickplace[1].planner_id = "RRTConnectkConfigDefault"
        self.pick_result = [None]*2
        self._last_gripper_picked = 0
        self.place_result = [None]*2
        self._last_gripper_placed = 0
        
        self._objs_to_keep = []
        
        self._listener = tf.TransformListener()

        self._lgripper = GripperActionClient('left')
        self._rgripper = GripperActionClient('right')
        
        find_topic = "basic_grasping_perception/find_objects"
        rospy.loginfo("Waiting for %s..." % find_topic)
        self.find_client = actionlib.SimpleActionClient(find_topic, FindGraspableObjectsAction)
        self.find_client.wait_for_server()
        
        self.scene.clear()
        
        # This is a simulation so need to adjust gripper parameters
        if sim:
            self._gripper_closed = 0.96
            self._gripper_open = 0.0
        else:
            self._gripper_closed = 0.0
            self._gripper_open = 0.165
            
    def add_objects_to_keep(self,obj):
        self._objs_to_keep.append(obj)

    def updateScene(self,gripper=0):
        # find objects
        goal = FindGraspableObjectsGoal()
        goal.plan_grasps = True
        goal.gripper = gripper
        self.find_client.send_goal(goal)
        self.find_client.wait_for_result(rospy.Duration(5.0))
        find_result = self.find_client.get_result()

        # remove previous objects
        for name in self.scene.getKnownCollisionObjects():
            print name
            self.scene.removeCollisionObject(name, True)

        # insert objects to scene
        idx = -1
        for obj in find_result.objects:
            if obj.object.primitive_poses[0].position.z < 0.5:
                continue
            idx += 1
            obj.object.name = "object%d_%d"%(idx,gripper)
            self.scene.addSolidPrimitive(obj.object.name,
                                         obj.object.primitives[0],
                                         obj.object.primitive_poses[0],
                                         wait = True)

        for obj in find_result.support_surfaces:
            # extend surface to floor, and make wider since we have narrow field of view
            if obj.primitive_poses[0].position.z < 0.1:
                continue
            height = obj.primitive_poses[0].position.z
            obj.primitives[0].dimensions = [obj.primitives[0].dimensions[0],
                                            obj.primitives[0].dimensions[1],  # wider
                                            obj.primitives[0].dimensions[2] + height]
            obj.primitive_poses[0].position.z += -height/2.0

            # add to scene
            self.scene.addSolidPrimitive(obj.name,
                                         obj.primitives[0],
                                         obj.primitive_poses[0],
                                         wait = True)

        self.scene.waitForSync()

        # store for grasping
        self.objects = find_result.objects
        self.surfaces = find_result.support_surfaces

    def getGraspableBeer(self):
        for obj in self.objects:
            # need grasps
            if len(obj.grasps) < 1:
                continue

            if (obj.object.primitives[0].type == sp.CYLINDER):
                if obj.object.primitives[0].dimensions[sp.CYLINDER_HEIGHT] < 0.102 or \
                   obj.object.primitives[0].dimensions[sp.CYLINDER_HEIGHT] > 0.142:
                    continue
            elif (obj.object.primitives[0].type == sp.BOX):
                if obj.object.primitives[0].dimensions[sp.BOX_Z] < 0.102 or \
                   obj.object.primitives[0].dimensions[sp.BOX_Z] > 0.142:
                    continue
            else:
                continue
           

            return obj.object, obj.grasps
        # nothing detected
        return None, None

    def getGraspablePringles(self):
        for obj in self.objects:
            # need grasps
            if len(obj.grasps) < 1:
                continue

            # has to be on table
            if obj.object.primitive_poses[0].position.z < 0.5:
                continue
            elif (obj.object.primitives[0].type == sp.CYLINDER):
                if obj.object.primitives[0].dimensions[sp.CYLINDER_HEIGHT] < 0.24 or \
                   obj.object.primitives[0].dimensions[sp.CYLINDER_HEIGHT] > 0.29:
                    continue
            elif (obj.object.primitives[0].type == sp.BOX):
                if obj.object.primitives[0].dimensions[sp.BOX_Z] < 0.24 or \
                   obj.object.primitives[0].dimensions[sp.BOX_Z] > 0.29:
                    continue
            else:
                continue

            return obj.object, obj.grasps
        # nothing detected
        return None, None

    def getSupportSurface(self, name):
        for surface in self.support_surfaces:
            if surface.name == name:
                return surface
        return None

    def getPlaceLocation(self):
        pass

    def pick(self, block, grasps, gripper=0):

        success, pick_result = self.pickplace[gripper].pick_with_retry(block.name,
                                                              grasps,
                                                              retries=1,
                                                              support_name=block.support_surface,
                                                              scene=self.scene)
        self.pick_result[gripper] = pick_result
        self._last_gripper_picked = gripper
        return success

    def place(self, block, pose_stamped,gripper=0):
        places = list()
        l = PlaceLocation()
        l.place_pose.pose = pose_stamped.pose
        l.place_pose.header.frame_id = pose_stamped.header.frame_id

        # copy the posture, approach and retreat from the grasp used
        l.post_place_posture = self.pick_result[gripper].grasp.pre_grasp_posture
        l.pre_place_approach = self.pick_result[gripper].grasp.pre_grasp_approach
        l.post_place_retreat = self.pick_result[gripper].grasp.post_grasp_retreat
        places.append(copy.deepcopy(l))
        # create another several places, rotate each by 360/m degrees in yaw direction
        m = 16 # number of possible place poses
        pi = 3.141592653589
        for i in range(0, m-1):
            l.place_pose.pose = rotate_pose_msg_by_euler_angles(l.place_pose.pose, 0, 0, 2 * pi / m)
            places.append(copy.deepcopy(l))

        success, place_result = self.pickplace[gripper].place_with_retry(block.name,
                                                                         places,
                                                                         retries=1,
                                                                         scene=self.scene)
        self.place_result[gripper] = place_result
        self._last_gripper_placed = gripper
        return success
    
    def goto_tuck(self):
        # remove previous objects
        jnt_pose = [-2.8,-1.48,-1.48,0,0,1.571,2.8,1.48,1.48,0,0,1.571,0.0371,0.0,0.0]
        while not rospy.is_shutdown():
            result = self.move_group.moveToJointPosition(self._upper_body_joints, jnt_pose, 0.05)
            if result.error_code.val == MoveItErrorCodes.SUCCESS:
                return
            
    def goto_plan_grasp(self):
        jnt_pose = [2.28,2.17,-2.56,-0.09,0.15,1.082,-2.28,-2.17,2.56,0.09,-0.15,2.06,0.45,0.0,0.0]

        while not rospy.is_shutdown():
            result = self.move_group.moveToJointPosition(self._upper_body_joints, jnt_pose, 0.05)    
            if result.error_code.val == MoveItErrorCodes.SUCCESS:
                return

    def left_arm_constrained_stow(self):
        jnt_pose = [-2.28,-2.17,2.56,0.09,-0.15,2.08]
        c1 = Constraints()
        c1.orientation_constraints.append(OrientationConstraint())
        c1.orientation_constraints[0].header.stamp = rospy.get_rostime()
        c1.orientation_constraints[0].header.frame_id = "base_link"
        c1.orientation_constraints[0].link_name = "left_ee_link"
        c1.orientation_constraints[0].orientation.w=1.0
        c1.orientation_constraints[0].absolute_x_axis_tolerance = 0.2 #x axis is pointed up for wrist link
        c1.orientation_constraints[0].absolute_y_axis_tolerance = 0.2
        c1.orientation_constraints[0].absolute_z_axis_tolerance = 6.28
        c1.orientation_constraints[0].weight = 1.0

        while not rospy.is_shutdown():
            result = self.lmove_group.moveToJointPosition(self._left_arm_joints, jnt_pose, 0.05, path_constraints=c1, planning_time=120.0)
            if result.error_code.val == MoveItErrorCodes.SUCCESS:
                return

    def right_arm_constrained_stow(self):
        jnt_pose = [2.28,2.17,-2.56,-0.09,0.15,1.06]
        c1 = Constraints()
        c1.orientation_constraints.append(OrientationConstraint())
        c1.orientation_constraints[0].header.stamp = rospy.get_rostime()
        c1.orientation_constraints[0].header.frame_id = "base_link"
        c1.orientation_constraints[0].link_name = "right_ee_link"
        c1.orientation_constraints[0].orientation.w=1.0
        c1.orientation_constraints[0].absolute_x_axis_tolerance = 0.2 #x axis is pointed up for wrist link
        c1.orientation_constraints[0].absolute_y_axis_tolerance = 0.2
        c1.orientation_constraints[0].absolute_z_axis_tolerance = 6.28
        c1.orientation_constraints[0].weight = 1.0

        while not rospy.is_shutdown():
            result = self.rmove_group.moveToJointPosition(self._right_arm_joints, jnt_pose, 0.05, path_constraints=c1, planning_time=120.0)
            if result.error_code.val == MoveItErrorCodes.SUCCESS:
                return
            
    def open_gripper(self):
        self._lgripper.command(self._gripper_open,block=True)
        self._rgripper.command(self._gripper_open,block=True)
        
    def close_gripper(self):
        self._lgripper.command(self._gripper_closed,block=True)
        self._rgripper.command(self._gripper_closed,block=True) 
        

if __name__ == "__main__":
    
    # Create a node
    rospy.init_node("demo")

    # Setup clients
    move_base = MoveBaseActionClient(sim=True)
    head_action = PointHeadClient()
    grasping_client = GraspingClient(sim=True)

    # Move the base to be in front of the table
    # Demonstrates the use of the navigation stack
    rospy.loginfo("Moving toward table...")
    target = Pose2D(x=2.0,y=3.2,theta=0.0)
    move_base.goto(target)
    grasping_client.goto_tuck()
    grasping_client.close_gripper()


    # set the robot pos to the planning pose
    grasping_client.goto_plan_grasp()
    grasping_client.open_gripper()
    rospy.loginfo("Moving up close to table...")
    target = Pose2D(x=3.0,y=3.2,theta=0.0)
    move_base.goto(target)
    
    # Point the head at the stuff we want to pick
    head_action.look_at(3.9, 3.2, 0.88, "map")

    # find stuff to pick
    while not rospy.is_shutdown():
        rospy.loginfo("Picking object...")
        grasping_client.updateScene(0)
        beer, grasps = grasping_client.getGraspableBeer()
        if beer == None:
            rospy.logwarn("Perception failed.")
            continue

        # Pick the beer
        if grasping_client.pick(beer, grasps,0):
            break
        rospy.logwarn("Grasping failed.")

    # Tuck the arm with constraints
    
    grasping_client.goto_plan_grasp()
    
    rospy.loginfo("Moving up close to table...")
    target = Pose2D(x=3.0,y=2.70,theta=0.0)
    move_base.goto(target)
    
    # Point the head at the stuff we want to pick
    head_action.look_at(3.9, 2.75, 0.95, "map")

    while not rospy.is_shutdown():
        rospy.loginfo("Picking object...")
        grasping_client.updateScene(1)
        pringles, grasps = grasping_client.getGraspablePringles()
        if pringles == None:
            rospy.logwarn("Perception failed.")
            continue

        # Pick the beer
        if grasping_client.pick(pringles, grasps,1):
            break
        rospy.logwarn("Grasping failed.")
        
    rospy.loginfo("Turning around...")
    target = Pose2D(x=2.0,y=2.70,theta=3.14)
    move_base.goto(target)
    
    grasping_client.goto_plan_grasp()
    
    # Move to second table
    rospy.loginfo("Moving to second table...")
    target = Pose2D(x=3.0, y=-1.8, theta=0.0)
    move_base.goto(target)
    
    # Point the head at the stuff we want to pick
    head_action.look_at(3.9, -1.8, 0.88, "map")
    
    # Place the block
    while not rospy.is_shutdown():
        grasping_client.updateScene(0)
        rospy.loginfo("Placing object...")
        pose = PoseStamped()
        pose.pose = beer.primitive_poses[0]
        pose.pose.position.z += 0.01
        pose.header.frame_id = beer.header.frame_id
        if grasping_client.place(beer, pose, gripper=0):
            break
        rospy.logwarn("Placing failed.")
        
    grasping_client.goto_plan_grasp()
    
    # Move to second table
    rospy.loginfo("Moving to second table...")
    target = Pose2D(x=3.0, y=-2.25, theta=0.0)
    move_base.goto(target)
    
    # Point the head at the stuff we want to pick
    head_action.look_at(3.9, -2.25, 0.88, "map")
    
    # Place the block
    while not rospy.is_shutdown():
        grasping_client.updateScene(1)
        rospy.loginfo("Placing object...")
        pose = PoseStamped()
        pose.pose = pringles.primitive_poses[0]
        pose.pose.position.z += 0.01
        pose.header.frame_id = pringles.header.frame_id
        if grasping_client.place(pringles, pose, gripper=1):
            break
        rospy.logwarn("Placing failed.")
        
    grasping_client.goto_plan_grasp()

    # Point the head at the stuff we want to pick
    head_action.look_at(3.9, -2.25, 0.88, "map")

    while not rospy.is_shutdown():
        rospy.loginfo("Picking object...")
        grasping_client.updateScene(1)
        pringles, grasps = grasping_client.getGraspablePringles()
        if pringles == None:
            rospy.logwarn("Perception failed.")
            continue

        # Pick the beer
        if grasping_client.pick(pringles, grasps,1):
            break
        rospy.logwarn("Grasping failed.")
    
    grasping_client.goto_plan_grasp()

    # Move to second table
    rospy.loginfo("Moving to second table...")
    target = Pose2D(x=3.0, y=-1.8, theta=0.0)
    move_base.goto(target)
    
    # Point the head at the stuff we want to pick
    head_action.look_at(3.9, -1.8, 0.88, "map")

    # find stuff to pick
    while not rospy.is_shutdown():
        rospy.loginfo("Picking object...")
        grasping_client.updateScene(0)
        beer, grasps = grasping_client.getGraspableBeer()
        if beer == None:
            rospy.logwarn("Perception failed.")
            continue

        # Pick the beer
        if grasping_client.pick(beer, grasps,0):
            break
        rospy.logwarn("Grasping failed.")

    rospy.loginfo("Turning around...")
    target = Pose2D(x=2.0,y=-1.8,theta=3.14)
    move_base.goto(target)
    
    grasping_client.goto_plan_grasp()
    
    # Move to second table
    rospy.loginfo("Moving to second table...")
    target = Pose2D(x=3.0,y=3.2,theta=0.0)
    move_base.goto(target)
    
    # Point the head at the stuff we want to pick
    head_action.look_at(3.9, 3.2, 0.88, "map")
    
    # Place the block
    while not rospy.is_shutdown():
        grasping_client.updateScene(0)
        rospy.loginfo("Placing object...")
        pose = PoseStamped()
        pose.pose = beer.primitive_poses[0]
        pose.pose.position.z += 0.01
        pose.header.frame_id = beer.header.frame_id
        if grasping_client.place(beer, pose, gripper=0):
            break
        rospy.logwarn("Placing failed.")
        
    grasping_client.goto_plan_grasp()
    
    # Move to second table
    rospy.loginfo("Moving to second table...")
    target = Pose2D(x=3.0,y=2.70,theta=0.0)
    move_base.goto(target)
    
    # Point the head at the stuff we want to pick
    head_action.look_at(3.9, 2.75, 0.95, "map")
    
    # Place the block
    while not rospy.is_shutdown():
        grasping_client.updateScene(1)
        rospy.loginfo("Placing object...")
        pose = PoseStamped()
        pose.pose = pringles.primitive_poses[0]
        pose.pose.position.z += 0.01
        pose.header.frame_id = pringles.header.frame_id
        if grasping_client.place(pringles, pose, gripper=1):
            break
        rospy.logwarn("Placing failed.")
        
    grasping_client.goto_plan_grasp()
    
    # Move the base to be in front of the table
    # Demonstrates the use of the navigation stack
    rospy.loginfo("Moving toward table...")
    target = Pose2D(x=2.0,y=3.2,theta=0.0)
    move_base.goto(target)
    grasping_client.goto_tuck()
    grasping_client.close_gripper()

    
        

