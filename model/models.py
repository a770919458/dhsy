from peewee import Model, SqliteDatabase, IntegerField, TextField, DateTimeField
from playhouse.fields import PickleField

db = SqliteDatabase("data/game.db")

class BaseModel(Model):
    class Meta:
        database = db

class MainMissionModel(BaseModel):
    title = TextField() #任务标题
    description = TextField() #任务详细信息
    point_x = IntegerField() #任务横向坐标
    point_y = IntegerField() #任务纵向坐标
    pass

class teamModel(BaseModel):
    task_name = TextField()
    leader_id = TextField()
    member_ids = PickleField(default=list)
    status = TextField()
    created_at = DateTimeField()
