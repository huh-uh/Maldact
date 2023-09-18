import multiprocessing

from backend.learn_network import LearnNetwork
from backend.network import Network
import numpy as np
import cupy as cp
import multiprocessing as mp
import inspect
from event_bus import EventBus as eb
import os
import queue
import PyQt5.QtCore as qtc


class TrainingManager:

    instance_id = 1

    def __init__(self, event=None, **kwargs):

        # ID assignment
        self.id = TrainingManager.instance_id
        TrainingManager.instance_id += 1

        # make LearnNetwork.learn() default arguments into attributes of TrainingManager
        self.network = LearnNetwork([1, 1])
        learn_signature = inspect.signature(self.network.learn)
        default_args = {param.name: param.default for param in learn_signature.parameters.values() if
                        param.default != inspect.Parameter.empty}
        for key, value in default_args.items():
            setattr(self, key, value)

        # additional attributes
        self.save_params = False
        self.data_dir = None
        self.model_dir = None
        self.model_name = None
        self.training_process = None
        self.term_queue = mp.Queue()
        self.check_timer = qtc.QTimer()

        # overwrite the default values
        for key, value in kwargs.items():
            if key in self.__dict__.keys():
                setattr(self, key, value)
            else:
                raise AttributeError(f"TrainingManager object has no attribute {key}")

        if event:
            eb.subscribe(event, self.start_training)

    def update_params(self, update_dict):

        for key, value in update_dict.items():
            if key in self.__dict__.keys():
                setattr(self, key, value)

    def start_training(self):

        try:
            if self.training_process.is_alive():
                return None
        except AttributeError:
            pass

        self.network.__init__(self.N, GPU=self.GPU)  # reinitialize network object
        training_data = np.load(self.data_dir)
        inp = training_data["input"]
        labels = training_data["labels"]
        exec_args = (
            inp,
            labels
        )
        self.training_process = mp.Process(
            target=self.executor,
            args=exec_args
        )

        self.training_process.start()
        self.check_timer.timeout.connect(self.check_queue)
        self.check_timer.start(100)

    def executor(self, inp, labels):

        arg_filter = lambda x: not callable(x) and not isinstance(x, LearnNetwork)
        kwargs = {key: value for key, value in self.__dict__.items() if arg_filter(value)}
        meta = self.network.learn(
            inp,
            labels,
            **kwargs
        )
        np.save(meta, os.path.join(self.model_dir, self.model_name))
        self.term_queue.put("done")

    def exit_training(self):
        pass  # TODO

    def check_queue(self):
        try:
            match self.term_queue.get():
                case "done":
                    eb.emit(f"training_done_{self.id}")
                    self.check_timer.stop()
                    if self.training_process.is_alive():
                        self.training_process.terminate()
        except queue.Empty:
            pass


class SortingManager:

    instance_id = 1

    def __init__(self, **kwargs):

        # ID assignment
        self.id = TrainingManager.instance_id
        TrainingManager.instance_id += 1

        # other attribute declarations
        self.network = Network(skip_init=True)
        self.model_file = None
        self.data_file = None
        self.sort_dir = None
        self.dir_name = None
        self.sorting_process = None
        self.term_queue = mp.Queue()
        self.check_timer = qtc.QTimer()

        # overwrite the default values
        for key, value in kwargs.items():
            if key in self.__dict__.keys():
                setattr(self, key, value)
            else:
                raise AttributeError(f"SortingManager object has no attribute {key}")

    def update_params(self, update_dict):

        for key, value in update_dict.items():
            if key in self.__dict__.keys():
                setattr(self, key, value)

    def start_sorting(self):

        try:
            if self.sorting_process.is_alive() is True:
                return None
        except AttributeError:
            pass

        self.network.load_params(self.model_file)
        self.dir_name = f"sorted_by_{self.model_file.os.path.basename(self.model_file)}"
        os.mkdir(os.path.join(self.sort_dir, self.dir_name))
        data = np.load(self.data_file)
        term_queue = mp.Queue()
        for i in range(self.network.N[-1]):
            os.mkdir(os.path.join(self.dir_name, str(i)))
        exec_args = (
            data,
            term_queue
        )
        self.sorting_process = mp.Process(
            target=self.executor,
            args=exec_args
        )
        self.sorting_process.start()

    def executor(self, data, queue):

        out = self.network.get_output(data)
        dim = out.shape[0]
        for i in range(dim):
            np.save(os.path.join(self.dir_name, str(np.argmax(out[i, :]))), out[i, :])
        queue.put("done")

    def check_queue(self):
        try:
            match self.term_queue.get():
                case "done":
                    eb.emit(f"sorting_done_{self.id}")
                    self.check_timer.stop()
                    if self.sorting_process.is_alive():
                        self.sorting_process.terminate()
        except queue.Empty:
            pass

