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
import smach
import smach_ros


class search_face(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded'])

    def execute(self, userdata):
        rospy.loginfo('Executing state SEARCH_FACE')
        rospy.sleep(5)
        return 'succeeded'


class move_closer(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['succeeded'])

    def execute(self, userdata):
        rospy.loginfo('Executing state MOVE_CLOSER')
        rospy.sleep(5)
        return 'succeeded'


def construct_sm():
    rospy.loginfo('Constructing state machine')
    sm = smach.StateMachine(outcomes = ['succeeded'])

    with sm:
        smach.StateMachine.add('SEARCH_FACE', search_face(), transitions={'succeeded':'MOVE_CLOSER'})
        smach.StateMachine.add('MOVE_CLOSER', move_closer(), transitions={'succeeded': 'succeeded'})

    return sm


if __name__ == "__main__":
    rospy.loginfo('initializing dance invitation')
    rospy.init_node('dance_invitation')

    sm = construct_sm()
    rospy.loginfo('State machine Constructed')


    # Run state machine introspection server for smach viewer
    intro_spect = smach_ros.IntrospectionServer('dance_invitation', sm, '/DANCE_INVITATION')
    intro_spect.start()
    outcome = sm.execute()

    rospy.spin()
    intro_spect.stop()

