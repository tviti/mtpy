# -*- coding: utf-8 -*-
"""
    Description:


    Usage:

    Author: YingzhiGou
    Date: 20/06/2017
"""

import abc

from PyQt4 import QtGui, QtCore

from mtpy.gui.SmartMT.gui.plot_parameter import PlotParameter
from mtpy.utils.mtpylog import MtPyLog
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT as NavigationToolbar

class VisualizationBase(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def __init__(self, parent):
        self._parent = parent
        self._mt_objs = None
        self._fig = None
        self._logger = MtPyLog().get_mtpy_logger(__name__)
        self._parameter_ui = PlotParameter(self._parent)
        # connect plot button
        QtCore.QObject.connect(self._parameter_ui.ui.pushButtonPlot, QtCore.SIGNAL("clicked()"), self.show_figure)

    def set_data(self, mt_objs):
        self._mt_objs = mt_objs
        self.update_ui()

    @abc.abstractmethod
    def update_ui(self):
        pass

    @abc.abstractproperty
    def parameter_ui(self):
        return "should not see this"

    @staticmethod
    @abc.abstractmethod
    def plot_name():
        return VisualizationBase.__name__

    @staticmethod
    @abc.abstractmethod
    def plot_description():
        return VisualizationBase.__name__

    # _plottingFinished = QtCore.pyqtSignal()

    # def _create_plot(self):
    #     self.plot()
        # self._plottingFinished.emit()

    @abc.abstractmethod
    def plot(self):
        pass

    def show_figure(self):
        progressbar = ProgressBar()
        progressbar.onStart()
        # self._plottingFinished.connect(progressbar.onFinished)
        # self._create_plot()
        self.plot()
        if self._fig:
            # self._fig.show()
            widget = QtGui.QWidget()
            layout = QtGui.QVBoxLayout()
            canvas = FigureCanvas(self._fig.get_figure())
            toolbar = NavigationToolbar(canvas, widget)
            layout.addWidget(toolbar)
            layout.addWidget(canvas)
            widget.setLayout(layout)

            progressbar.onFinished()

            self._parent._parent.create_subwindow(widget, self.plot_name(), overide=False)
        else:
            progressbar.onFinished()


class ProgressBar(QtGui.QWidget):
    def __init__(self, parent=None):
        super(ProgressBar, self).__init__(parent)
        layout = QtGui.QVBoxLayout(self)
        self.progressbar = QtGui.QProgressBar(self)
        self.progressbar.setRange(0, 1)
        layout.addWidget(self.progressbar)

    def onStart(self):
        self.progressbar.setRange(0, 0)
        self.progressbar.show()

    def onFinished(self):
        self.progressbar.setRange(0, 1)
        self.progressbar.hide()
