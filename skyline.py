import argparse
import datetime
import math
import os
import subprocess
from calendar import monthrange
from collections import defaultdict, namedtuple

import gpxpy
import stravalib
from solid import scad_render_to_file
from solid.utils import cube, linear_extrude, polyhedron, rotate, text, translate

ACTIVITY_NAME_TUPLE = namedtuple("activity", "date distance")


def generate_skyline_stl(username, year, running_matrix):
    """
    Some code of this function is from https://github.com/felixgomez/gitlab-skyline
    """
    max_run_distance = max(running_matrix)
    total_run_distance = sum(running_matrix)
    base_top_width = 23
    base_width = 30
    base_length = 150
    base_height = 10
    max_length_run_distance = 40
    bar_base_dimension = 2.5

    base_top_offset = (base_width - base_top_width) / 2
    face_angle = math.degrees(math.atan(base_height / base_top_offset))

    base_points = [
        [0, 0, 0],
        [base_length, 0, 0],
        [base_length, base_width, 0],
        [0, base_width, 0],
        [base_top_offset, base_top_offset, base_height],
        [base_length - base_top_offset, base_top_offset, base_height],
        [base_length - base_top_offset, base_width - base_top_offset, base_height],
        [base_top_offset, base_width - base_top_offset, base_height],
    ]

    base_faces = [
        [0, 1, 2, 3],  # bottom
        [4, 5, 1, 0],  # front
        [7, 6, 5, 4],  # top
        [5, 6, 2, 1],  # right
        [6, 7, 3, 2],  # back
        [7, 4, 0, 3],  # left
    ]

    base_scad = polyhedron(points=base_points, faces=base_faces)

    year_scad = rotate([face_angle, 0, 0])(
        translate(
            [
                base_length - base_length / 5,
                base_height / 2 - base_top_offset / 2 - 1,
                -1.5,
            ]
        )(linear_extrude(height=2)(text(str(year), 6)))
    )

    user_scad = rotate([face_angle, 0, 0])(
        translate([base_length / 4, base_height / 2 - base_top_offset / 2, -1.5])(
            linear_extrude(height=2)(text("@" + username, 5))
        )
    )

    total_scad = rotate([face_angle, 0, 0])(
        translate(
            [
                base_length - base_length / 3 - 17,
                base_height / 2 - base_top_offset / 2,
                -1.5,
            ]
        )(linear_extrude(height=2)(text(str(round(total_run_distance, 1)) + " km", 5)))
    )

    running_scad = rotate([face_angle, 0, 0])(
        translate([base_length / 12, base_height / 2 - base_top_offset / 2, -1])(
            linear_extrude(height=2)(text("Running", 5))
        )
    )

    bars = None

    week_number = 1
    for i in range(len(running_matrix)):

        day_number = i % 7
        if day_number == 0:
            week_number += 1

        if running_matrix[i] == 0:
            continue

        bar = translate(
            [
                base_top_offset + 2.5 + (week_number - 1) * bar_base_dimension,
                base_top_offset + 2.5 + day_number * bar_base_dimension,
                base_height,
            ]
        )(
            cube(
                [
                    bar_base_dimension,
                    bar_base_dimension,
                    running_matrix[i] * max_length_run_distance / max_run_distance,
                ]
            )
        )

        if bars is None:
            bars = bar
        else:
            bars += bar

    scad_running_filename = "running_" + username + "_" + str(year)
    scad_skyline_object = base_scad - running_scad + user_scad + total_scad + year_scad

    if bars is not None:
        scad_skyline_object += bars

    scad_render_to_file(scad_skyline_object, scad_running_filename + ".scad")

    subprocess.run(
        [
            "openscad",
            "-o",
            scad_running_filename + ".stl",
            scad_running_filename + ".scad",
        ]
    )

    print("Generated STL file " + scad_running_filename + ".stl")


class RunningSkyline:
    def __init__(self, year=2020, base_dir="GPX_DIR"):
        self.base_dir = base_dir
        self.client = stravalib.Client()
        self.year = year
        self.strava_access = False
        self.date_distance_dict = defaultdict(float)
        self.activities_get_dict = {
            "strava": self.__make_strava_activites,
            "gpx": self.__make_gpx_activites,
        }

    def set_strava_config(self, client_id, client_secret, refresh_token):
        if not all([client_id, client_secret, refresh_token]):
            raise Exception(
                "Please set all the client_id, client_secret, refresh_token"
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

    def _make_year_before_after(self):
        self.before = datetime.datetime(int(self.year) + 1, 1, 1)
        self.after = datetime.datetime(int(self.year), 1, 1)

    def _get_all_year_dates(self):
        for month in range(1, 13):
            for day in range(1, monthrange(self.year, month)[1] + 1):
                yield datetime.datetime(self.year, month, day).date()

    def _get_access(self):
        try:
            response = self.client.refresh_access_token(
                client_id=self.client_id,
                client_secret=self.client_secret,
                refresh_token=self.refresh_token,
            )
        except:
            raise Exception("Something is wrong with your auth please check")

        self.access_token = response["access_token"]
        self.refresh_token = response["refresh_token"]
        self.client.access_token = response["access_token"]
        self.strava_access = True

    def get_strava_activities(self):
        if not self.strava_access:
            self._get_access()
        # make year range
        self._make_year_before_after()
        return self.client.get_activities(before=self.before, after=self.after)

    def __make_strava_activites(self):
        activites = list(self.get_strava_activities())
        activites.reverse()
        activites = [
            ACTIVITY_NAME_TUPLE(a.start_date_local.date(), a.distance)
            for a in activites
        ]
        return activites

    def _make_activites_date_dict(self, type_name):
        # for different type `gpx` or `strava`
        activites = self.activities_get_dict.get(type_name, "strava")()
        for a in activites:
            # maybe one day run some times
            self.date_distance_dict[a.date] += float(a.distance)

    def make_stl_matrix_list(self):
        if not self.date_distance_dict:
            self._make_activites_date_dict()
        year_date_list = list(self._get_all_year_dates())
        date_matrix_list = []
        for d in year_date_list:
            if d in self.date_distance_dict:
                date_matrix_list.append(round(self.date_distance_dict[d] / 1000, 1))
            else:
                date_matrix_list.append(0)
        return date_matrix_list

    def _list_gpx_files(self):
        base_dir = os.path.abspath(self.base_dir)
        if not os.path.isdir(base_dir):
            raise Exception(f"Not a directory: {base_dir}")
        for name in os.listdir(base_dir):
            if name.startswith("."):
                continue
            path_name = os.path.join(base_dir, name)
            if name.endswith(".gpx") and os.path.isfile(path_name):
                yield path_name

    @staticmethod
    def __parse_gpx(file_name):
        with open(file_name) as f:
            gpx = gpxpy.parse(f)
            try:
                start_time, _ = gpx.get_time_bounds()
                distance = gpx.length_2d()
            except Exception as e:
                print(f"Something is wrong when loading file {file_name}", str(e))
        return start_time.date(), distance

    def __make_gpx_activites(self):
        files = list(self._list_gpx_files())
        activites = []
        print("Loading your gpx files it may take a little time please wait")
        for f in files:
            date, distance = self.__parse_gpx(f)
            # filter
            if date.year != self.year:
                continue
            activites.append(ACTIVITY_NAME_TUPLE(date, distance))
        return activites


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--type",
        dest="type",
        type=str,
        choices=["strava", "gpx"],
        default="gpx",
        help="running type strava or gpx",
    )
    parser.add_argument(
        "--runner", dest="runner", help="runner's name", default="Runner", required=False
    )
    parser.add_argument(
        "--client_id",
        dest="client_id",
        help="strava client_id",
        default="",
        required=False,
    )
    parser.add_argument(
        "--client_secret",
        dest="client_secret",
        help="strava client_secret",
        default="",
        required=False,
    )
    parser.add_argument(
        "--refresh_token",
        dest="refresh_token",
        help="strava refresh_token",
        default="",
        required=False,
    )
    parser.add_argument(
        "--year", dest="year", help="strava or gpx running year", type=int, default=2020
    )
    parser.add_argument(
        "--gpx-dir",
        dest="gpx_dir",
        metavar="DIR",
        type=str,
        default="GPX_DIR",
        help="Directory containing GPX files (default: current directory).",
    )

    options = parser.parse_args()
    if len(options.runner) > 10:
        raise Exception("Please make sure your runner name < 9 for stl")
    skyline = RunningSkyline(year=options.year, base_dir=options.gpx_dir)
    if options.type == "strava":
        skyline.set_strava_config(
            options.client_id, options.client_secret, options.refresh_token
        )
    skyline._make_activites_date_dict(options.type)
    running_matrix_list = skyline.make_stl_matrix_list()
    generate_skyline_stl(options.runner, options.year, running_matrix_list)
