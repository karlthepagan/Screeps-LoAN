import click
from screeps_loan import app
import screepsapi.screepsapi as screepsapi
from screeps_loan.models.db import get_conn
from screeps_loan.screeps_client import get_client
from screeps_loan.models import db
from screeps_loan.services.cache import cache

import screeps_loan.models.alliances as alliances
import screeps_loan.models.users as users


@cache.cache('getUserControlPoints')
def getUserControlPoints(username):
    screeps = get_client()
    user_info = screeps.user_find(username)
    if 'user' in user_info:
        if 'gcl' in user_info['user']:
            return user_info['user']['gcl']
    return 1


class Rankings(object):
    gclcache = {}

    def run(self):

        alliance_query = alliances.AllianceQuery()
        all_alliances = alliance_query.getAll()
        alliances_names = [item["shortname"] for item in all_alliances]
        users_with_alliance = users.UserQuery().find_name_by_alliances(alliances_names)

        query = "SELECT id FROM room_imports WHERE status LIKE 'complete' ORDER BY started_at DESC"
        result = db.find_one(query)
        self.room_import_id = result[0]


        self.conn = get_conn()
        self.start()
        print(self.id)


        for alliance in all_alliances:
            users_with_alliance = self.find_name_by_alliances(alliances_names)
            members = [user['name'] for user in users_with_alliance if user['alliance'] == alliance['shortname']]

            # Not enough members.
            if len(members) < 2:
                continue

            # Not enough rooms
            if self.get_room_count(alliance['shortname']) < 2:
                continue

            rcl = self.getAllianceRCL(alliance['shortname'])
            combined_gcl = sum(self.getUserGCL(user) for user in members)
            control = sum(getUserControlPoints(user) for user in members)
            alliance_gcl = self.convertGcl(control)
            spawns = self.getAllianceSpawns(alliance['shortname'])

            print('%s- %s, %s, %s, %s, %s' % (alliance['shortname'], combined_gcl, alliance_gcl, rcl, spawns, len(members)))

            self.update(alliance['shortname'], alliance_gcl, combined_gcl, rcl, spawns, len(members))

        self.finish()
        self.conn.commit()

    def start(self):
        query = "INSERT INTO rankings_imports(status) VALUES ('in progress') RETURNING id"
        cursor = self.conn.cursor()
        cursor.execute(query)
        self.id = cursor.fetchone()[0]

    def finish(self):
        query = "UPDATE rankings_imports SET status='complete' WHERE id=(%s)"
        cursor = self.conn.cursor()
        cursor.execute(query, (self.id, ))

    def update(self, alliance, alliance_gcl, combined_gcl, rcl, spawns, members):
        # Store info in db
        cursor = self.conn.cursor()
        query = "INSERT INTO rankings(import, alliance, alliance_gcl, combined_gcl, rcl, spawns, members) VALUES(%s, %s, %s, %s, %s, %s, %s)"
        cursor.execute(query, (self.id, alliance, alliance_gcl, combined_gcl, rcl, spawns, members))

    def getAllianceRCL(self, alliance):
        query = "SELECT SUM(level) FROM rooms, users WHERE rooms.owner = users.id AND users.alliance=%s AND rooms.import=%s"
        cursor = self.conn.cursor()
        cursor.execute(query, (alliance, self.room_import_id))
        result = cursor.fetchone()[0]
        if result is not None:
            return result
        return 0

    def getAllianceSpawns(self, alliance):
        count = 0
        query = "SELECT COUNT(*) FROM rooms, users WHERE rooms.owner = users.id AND users.alliance=%s AND level>=8 AND rooms.import=%s"
        cursor = self.conn.cursor()
        cursor.execute(query, (alliance, self.room_import_id))
        result = cursor.fetchone()[0]
        if result is not None:
            if result:
                count += result*3

        query = "SELECT COUNT(*) FROM rooms, users WHERE rooms.owner = users.id AND users.alliance=%s AND level=7 AND rooms.import=%s"
        cursor = self.conn.cursor()
        cursor.execute(query, (alliance, self.room_import_id))
        result = cursor.fetchone()[0]
        if result is not None:
            if result:
                count += result*2

        query = "SELECT COUNT(*) FROM rooms, users WHERE rooms.owner = users.id AND users.alliance=%s AND level>=1 AND level<7 AND rooms.import=%s"
        cursor = self.conn.cursor()
        cursor.execute(query, (alliance, self.room_import_id))
        result = cursor.fetchone()[0]
        if result is not None:
            if result:
                count += result

        return count



    def convertGcl(self, control):
        return int((control/1000000) ** (1/2.4))+1


    def getUserGCL(self, username):
        return self.convertGcl(getUserControlPoints(username))


    def find_name_by_alliances(self, alliance):
        query = "SELECT ign, alliance FROM users where alliance = ANY(%s)"
        cursor = self.conn.cursor()
        cursor.execute(query, (alliance,))
        result = cursor.fetchall()
        return [{"name": row[0], "alliance": row[1]} for row in result]


    def get_room_count(self, alliance):
        query = '''
        SELECT COUNT(DISTINCT rooms.name)
            FROM rooms,users
            WHERE rooms.owner=users.id
                AND users.alliance=%s
                AND rooms.import = (SELECT id
                                        FROM room_imports
                                        ORDER BY id desc
                                        LIMIT 1
                                    );
        '''
        cursor = self.conn.cursor()
        cursor.execute(query, (alliance,))
        result = cursor.fetchone()
        return int(result[0])



@app.cli.command()
def import_rankings():
    click.echo("Generating Rankings")
    r = Rankings()
    r.run()

