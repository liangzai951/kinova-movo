#!/usr/bin/env python
"""--------------------------------------------------------------------
Copyright (c) 2018, Kinova Robotics inc.

All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.
    * Neither the name of the copyright holder nor the names of its contributors
      may be used to endorse or promote products derived from this software
      without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

 \file   dance invitagion

 \Author Longfei Zhao

 \Platform: Linux/ROS Indigo
--------------------------------------------------------------------"""
import rospy
import roslaunch
import rospkg
import smach
import smach_ros


class SearchFace(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded'], input_keys=['uuid', 'launch_face_tracking_path'])

    def execute(self, userdata):
        rospy.loginfo('Executing state SEARCH_FACE')

        # create launch file handles
        launch_face_tracking = roslaunch.parent.ROSLaunchParent(userdata.uuid, [userdata.launch_face_tracking_path])

        launch_face_tracking.start()
        rospy.sleep(30)
        launch_face_tracking.shutdown()
        rospy.sleep(2)

        return 'succeeded'


class MoveCloser(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded'])

    def execute(self, userdata):
        rospy.loginfo('Executing state MOVE_CLOSER')
        rospy.sleep(2)
        return 'succeeded'

class DanceInvitation():
    def __init__(self):
        rospy.on_shutdown(self._shutdown)

        # # create roslaunch handles
        self._uuid = roslaunch.rlutil.get_or_generate_uuid(None, False)
        roslaunch.configure_logging(self._uuid)

        # construct state machine
        self._sm = self._construct_sm()
        rospy.loginfo('State machine Constructed')

        # Run state machine introspection server for smach viewer
        self._intro_spect = smach_ros.IntrospectionServer('dance_invitation', self._sm, '/DANCE_INVITATION')
        self._intro_spect.start()
        outcome = self._sm.execute()

        rospy.spin()
        self._intro_spect.stop()


    def _shutdown(self):
        # self._intro_spect.stop()
        pass

    def _construct_sm(self):
        rospy.loginfo('Constructing state machine')
        sm = smach.StateMachine(outcomes = ['succeeded'])

        # create launch file handles
        sm.userdata.launch_face_tracking_path = rospkg.RosPack().get_path('movo_demos') + '/launch/face_tracking/face_tracking.launch'
        sm.userdata.uuid = self._uuid

        with sm:
            smach.StateMachine.add('SEARCH_FACE', SearchFace(), transitions={'succeeded': 'MOVE_CLOSER'}, remapping = {'launch_face_tracking_path':'launch_face_tracking_path'})
            smach.StateMachine.add('MOVE_CLOSER', MoveCloser(), transitions={'succeeded': 'succeeded'})

        return sm


if __name__ == "__main__":
    rospy.loginfo('start dance invitation')
    rospy.init_node('dance_invitation', log_level=rospy.INFO)
    # rospy.init_node('dance_invitation', log_level=rospy.DEBUG)

    DanceInvitation()



