#!/usr/bin/env python3

from darwinpush import Client, Listener
from darwinpush.messages.AssociationMessage import AssociationCategory
from models import *

import os
import queue
import time
import pickle
import datetime

class MyListener(Listener):
    def __init__(self, q, quit):
        print("Setting Up")
        super().__init__(q, quit)

    @db.transaction()
    def on_schedule_message(self, m, source):
        # print("Schedule Message", m.rid)

        # We try to find a schedule, and replace it if we do
        found = (Schedule
                .select()
                .where(
                    Schedule.uid == m.uid,
                    Schedule.rid == m.rid
                ))

        count = found.count()
        if count > 0:
            # assert(count == 1)
            # s = found[0]

            # # print("Removing calling points")

            # # Removing all relevant calling points
            # CallingPoint.delete().where(
            #     CallingPoint.schedule == s
            # ).execute()
            return # TODO: Update calling points 

        else:
            s = Schedule()
            s.uid = m.uid
            s.rid = m.rid

        s.headcode = m.headcode
        s.start_date = m.start_date
        s.toc_code = m.toc_code
        s.category = m.category
        s.status = m.status
        s.active = m.active
        s.deleted = m.deleted
        s.cancel_tiploc = m.cancel_reason_tiploc
        s.cancel_code = m.cancel_reason_code
        s.cancel_near = m.cancel_reason_near
        s.save()

        for o in m.all_points:
            p = CallingPoint()
            p.tiploc = o.tiploc
            p.schedule = s
            p.activity_codes = o.planned_activity_codes
            p.cancelled = o.cancelled
            p.false_tiploc = o.false_tiploc
            p.route_delay = o.route_delay
            p.working_arrival = o.raw_working_arrival_time
            p.working_pass = o.raw_working_pass_time
            p.working_departure = o.raw_working_departure_time
            p.public_arrival = o.raw_public_arrival_time
            p.public_departure = o.raw_public_departure_time
            p.type = str(type(o))
            p.save()

    @db.transaction()
    def on_deactivated_message(self, message, source):
        # # print("Deactivated message", source)
        # d = DeactivatedSchedule()
        # d.rid = message.rid
        # d.save()
        pass

    @db.transaction()
    def on_association_message(self, message, source):
        # # print("Association message", source)
        # main_svc = build_assoc_svc(message.main_service)
        # assoc_svc = build_assoc_svc(message.associated_service)

        # main_svc.save()
        # assoc_svc.save()

        # a = Association()
        # a.main_service = main_svc
        # a.associated_service = assoc_svc
        # a.tiploc = message.tiploc
        # a.category = message.category
        # a.deleted = message.deleted
        # a.save()
        pass

    @db.transaction()
    def on_alarm_message(self, message, source):
        # # print("Alarm message", source)
        # a = Alarm()
        # a.action = message.alarm_action
        # a.type = message.alarm_type
        # a.aid = a.aid
        # a.save()
        pass

    def on_station_message(self, message, source):
        # # print("Station message", source)
        # s = Station()
        # s.stations = message.stations
        # s.message = str(message.message)
        # s.smid = message.smid
        # # TODO: Change to actual category and severity types
        # s.category = str(message.category)
        # s.severity = str(message.severity)
        # s.save()
        pass

    @db.transaction()
    def on_tracking_id_message(self, message, source):
        # print("Tracking ID message", source)
        pass

    @db.transaction()
    def on_train_alert_message(self, message, source):
        # print("Train alert message", source)
        pass

    @db.transaction()
    def on_train_order_message(self, message, source):
        # # print("Train order message", source)

        # first = None
        # second = None
        # third = None

        # if message.first:
        #     first = build_train_order_item(message.first)
        #     first.save()

        # if message.second:
        #     second = build_train_order_item(message.second)
        #     second.save()

        # if message.third:
        #     third = build_train_order_item(message.third)
        #     third.save()


        # t = TrainOrder()
        # t.first = first
        # t.second = second
        # t.third = third
        # # TODO: Change action to be set/clear
        # t.action = message.action
        # t.tiploc = message.tiploc
        # t.crs = message.crs
        # t.platform = message.platform
        # t.save()
        pass

    @db.transaction()
    def on_train_status_message(self, message, source):
        # print("Train Status Message", message._xml)

        # Save late reason in the database
        # save_train_status(message)

        late_reason = message.late_reason
        if not (late_reason and late_reason.code):
            # If it's not late we don't need to store anything...
            # print("SKIPPIN'", message.rid)
            return

        late_code = late_reason.code
        rid = message.rid

        for location in message.locations:

            tiploc = location.tiploc
            working_departure = location.working_departure_time

            if not working_departure:
                # The only ones we care about are the ones with updates on working departure
                continue

            calling_points = (CallingPoint.select(CallingPoint, Schedule)
                                .join(Schedule)
                                .where(CallingPoint.tiploc==tiploc, Schedule.rid==rid))

            # TODO:
            # There are some scenarios where a TIPLOC is repeated multiple times in a stop, such as UID=G68274 where train passes 4 times through AYRR. This case needs to be sorted.
            # For now we just modify the first instance

            if calling_points.count() == 0:
                # TODO: Deal with this error, as this should always be > 1
                continue

            # print(message._xml)
            calling_point = calling_points[0]

            if not calling_point.working_departure or calling_point.working_departure == working_departure:
                continue

            calling_point.actual_working_departure = working_departure
            calling_point.late_code = late_code
            calling_point.save()

        
def save_train_status(message):
    late_reason = message.late_reason
    lr = None

    if late_reason:
        lr = LateReason()
        lr.code = late_reason.code
        lr.tiploc = late_reason.tiploc
        lr.near = late_reason.near
        lr.save()

    t = TrainStatus()
    t.late_reason = lr
    t.rid = message.rid
    t.uid = message.uid
    t.start = message.start_date
    t.reverse_formation = message.reverse_formation
    t.save()

    for location in message.locations:
        # Building forecasts
        f_arrival = None
        f_departure = None
        f_pass = None

        if location.forecast_arrival_time:
            f_arrival = build_forecast(location.forecast_arrival_time)
            f_arrival.save()

        if location.forecast_departure_time:
            f_departure = build_forecast(location.forecast_departure_time)
            f_departure.save()

        if location.forecast_pass_time:
            f_pass = build_forecast(location.forecast_pass_time)
            f_pass.save()

        # Building platform
        platform = location.platform
        p = None

        if platform:
            p = Platform()
            p.source = platform.source or ""
            p.suppressed = platform.suppressed
            p.suppressed_by_cis = platform.suppressed_by_cis
            p.confirmed = platform.confirmed
            p.number = platform.number
            p.save()

        # Building location
        l = Location()
        l.train_status = t
        l.platform = p
        l.forecast_arrival = f_arrival
        l.forecast_departure = f_departure
        l.forecast_pass = f_pass
        l.tiploc = location.tiploc
        l.suppressed = location.suppressed
        l.detach_front = location.detach_front
        l.working_arrival = location.working_arrival_time
        l.working_departure = location.working_departure_time
        l.working_pass = location.working_pass_time
        l.public_arrival = location.public_arrival_time
        l.public_departure = location.public_departure_time
        l.length = location.length
        l.save()

def build_assoc_svc(assoc_svc):
    a = AssociationService()
    a.rid = assoc_svc.rid
    a.working_arrival = assoc_svc.working_arrival_time
    a.working_departure = assoc_svc.working_departure_time
    a.working_pass = assoc_svc.working_pass_time
    a.public_arrival = assoc_svc.public_arrival_time
    a.public_departure = assoc_svc.public_departure_time
    return a

def build_forecast(forecast):
    f = Forecast()
    f.source = forecast.source or ""
    f.source_cis = forecast.source_cis
    f.estimated = forecast.estimated_time
    f.working_estimated = forecast.working_estimated_time
    f.actual = forecast.actual_time
    f.actual_removed = forecast.actual_time_removed
    f.manual_estimated = forecast.manual_estimate_lower_limit_minutes
    f.manual_delay = forecast.manual_estimate_unknown_delay
    return f

def build_train_order_item(train_order):
    to = TrainOrderItem()
    to.rid = train_order.rid
    to.headcode = train_order.headcode
    to.working_arrival = train_order.working_arrival_time
    to.working_departure = train_order.working_departure_time
    to.working_pass = train_order.working_pass_time
    to.public_arrival = train_order.public_arrival_time
    to.public_departure = train_order.public_departure_time
    return to

# Make this file importable for debugging

class HPClient(Client):
    def on_disconnected(self):
        self.reconnect(retries=0, delay=10) # try to reconnect forever

if __name__ == "__main__":

    # Instantiate the Push Port client.
    client = HPClient(os.environ["STOMP_USER"],
                    os.environ["STOMP_PASS"],
                    os.environ["STOMP_QUEUE"],
                    MyListener)

    # Disable default reconnection attempts of Client
    client.auto_retry = False

    # Attempt to figure out downtime:
    # try:
    #     with open("downtime.pickle", "rb") as f:
    #         shutdown_at = pickle.load(f)
    #         downtime = datetime.datetime.now() - shutdown_at
    # except:
    #     print("Couldn't open downtime. Downloading all logs")
    #     downtime = 3600*24*2 # 2 days, big enough for all logs

    # Connect the Push Port client.
    # client.connect(downtime)
    client.connect()

    print("Connected")
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):

        print("Saving time of shutdown")
        try:
            with open("downtime.pickle", "wb") as f:
                pickle.dump(datetime.datetime.now(), f)
        except:
            print("Couldn't save downtime.")

        print("Disconnecting client...")
        client.disconnect()
        print("Bye")
