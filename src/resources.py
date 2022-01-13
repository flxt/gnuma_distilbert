from flask import request
from flask_restful import Resource, abort

from sqlitedict import SqliteDict
import uuid

from queue import Queue
import os
import logging

from src.training_help import InterruptState, QueueElement, delete_model


# Abort if a json file is expected, but not part of the request
def abort_not_json():
    abort(400, message='Only accepting requests with mime type application/json.')
    logging.error('Only accepting requests with mime type application/json.')

# Abort if expected parameter is missing from the request.
def abort_missing_parameter(parameter_name: str):
    abort(400, message=f'Expected "{parameter_name}" to be part of the request body.')
    logging.error(f'Expected "{parameter_name}" to be part of the request body.')

# Abort if specified model doesnt exist.
def abort_wrong_model_id(model_id: str):
    abort(400, message=f'No model with ÍD "{model_id}" exists.')
    logging.error('No model with ÍD "{model_id}" exists.')

# Abort wrong model for operation
def abort_wrong_op_type(model_id: str, op_type: str, status: str):
    abort(400, message = f'Can not {status} for model {model_id} with status {status}.')
    logging.error(f'Can not {status} for model {model_id} with status {status}.')

# API enpoint where only a model ID is given
class Base(Resource):

    # Return the decription and more info for the model with the given id
    def get(self, model_id: str):
        # check if model exists
        if not model_id in SqliteDict('./distilBERT.sqlite').keys():
            abort_wrong_model_id(model_id)

        # get info for model from db
        model_info = SqliteDict('./distilBERT.sqlite')[model_id]

        return model_info

    # Delete the model with the specified id
    def delete(self, model_id: str):
        # check if model exists
        if not model_id in SqliteDict('./distilBERT.sqlite').keys():
            abort_wrong_model_id(model_id)

        delete_model(model_id)

        return {'model_id':model_id, 'operation':'deleted'}


class Continue(Resource):

    # init the resource
    def __init__(self, que: Queue):
        self._q = que
        self._op_type = 'continue'

    # Continue the training of the classifiers with the specified id.
    def post(self, model_id: str):
        # Check if model exists
        if not model_id in SqliteDict('./distilBERT.sqlite').keys():
            abort_wrong_model_id(model_id)

        # Check if model was interruptd
        if (SqliteDict('./distilBERT.sqlite')[model_id]['status'] != 'interrupted'):
            abort_wrong_op_type(model_id, self._op_type, SqliteDict('./distilBERT.sqlite')[model_id][status])

        # put training request in the que
        self._q.put(QueueElement(model_id, self._op_type))

        logging.info(f'Put model {model_id} in queue to continue training')

        return {'model_id':model_id, 'operation':'continue'}


# API endpoint for interrupting the training to continue later
class Pause(Resource):

    # init the resource
    def __init__(self, stop: InterruptState):
        self._stop = stop

    # Interrupt the training and save the model to continue it later
    def patch(self):
        self._stop.set_state(1)
        logging.info('Interruption signal sent.')
        return {'model_id':model_id, 'operation':'pause'}


# API endpoint for interrupting the training
class Interrupt(Resource):

    # init the resource
    def __init__(self, stop: InterruptState):
        self._stop = stop

    # Interrupt the Training and discard the model.
    def delete(self):
        self._stop.set_state(2)
        logging.info('Interruption and deletion signal sent')
        return {'model_id':model_id, 'operation':'interrupt'}


# API endpoint for classifying data wiht a specified model
class Predict(Resource):

    # Init the resource
    def __init__(self, que: Queue):
        self._q = que
        self._op_type = 'predict'

    # Predict data wiht a specified model
    def get(self, model_id: str):
        # check if model exists
        if not model_id in SqliteDict('./distilBERT.sqlite').keys():
            abort_wrong_model_id(model_id)

        # Check if model is trained
        if (SqliteDict('./distilBERT.sqlite')[model_id]['status'] != 'trained'):
            abort_wrong_op_type(model_id, self._op_type, SqliteDict('./distilBERT.sqlite')[model_id][status])

        # put prediction request in the que
        self._q.put(QueueElement(model_id, self._op_type))

        logging.info(f'Put model {model_id} in queue for prediction')

        return {'model_id':model_id, 'operation':'predict'}


# API endpoint for given some labeled data for testing to the model.
class Evaluate(Resource):

    # Init the resource
    def __init__(self, que: Queue):
        self._q = que
        self._op_type = 'evaluate'

    # Evaluate the model with the given data and return some performance information
    def get(self, model_id: str):
        # check if model exists
        if not model_id in SqliteDict('./distilBERT.sqlite').keys():
            abort_wrong_model_id(model_id)

        # Check if model is trained
        if (SqliteDict('./distilBERT.sqlite')[model_id]['status'] != 'trained'):
            abort_wrong_op_type(model_id, self._op_type, SqliteDict('./distilBERT.sqlite')[model_id][status])

        # Put evaluation request in que
        self._q.put(QueueElement(model_id, self._op_type))

        logging.info(f'Put model {model_id} in queue for evaluation')

        return {'model_id':model_id, 'operation':'evaluate'}


# API endpoint for returning a list of all saved models.
class List(Resource):
    # Return a list of all saved models
    def get(self):
        model_list = []

        with SqliteDict('./distilBERT.sqlite') as db:
            for model_id in db.keys():
                model_list.append({'model_id': model_id, 'model_name': db[model_id]['model_name'], 'data': db[model_id]['data_location'], 'status': db[model_id]['status']})

        return model_list


# API endpoint for training a new model.
class Train(Resource):

    # init the resource
    def __init__(self, que: Queue):
        self._q = que
        self._op_type = 'train'

    # Train a new Classifier
    def post(self):
        # check for json file
        if not request.is_json:
            return abort_not_json()

        req = request.json

        if 'model_name' not in req:
            abort_missing_parameter('model_name')

        if 'data_location' not in req:
            abort_missing_parameter('data_location')

        # Generate a random model id
        model_id = str(uuid.uuid4())

        # Save the model info
        with SqliteDict('./distilBERT.sqlite') as db:
            req['model_id'] = model_id
            db[model_id] = req
            db.commit()

        # Put training request in the que
        self._q.put(QueueElement(model_id, self._op_type))

        logging.info(f'Put model {model_id} in queue for training')

        return {'model_id':model_id, 'operation':'train'}