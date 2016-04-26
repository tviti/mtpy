# -*- coding: utf-8 -*-
"""
Created on Mon Mar 28 15:04:27 2016

@author: jpeacock
"""

#==============================================================================
#  Imports
#==============================================================================

from PyQt4 import QtCore, QtGui
import mtpy.core.mt as mt
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QTAgg as NavigationToolbar
from matplotlib.figure import Figure
import mtpy.imaging.mtplottools as mtplt
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import copy
import sys
import os
import mtpy.imaging.plotstrike2d as plotstrike2d

#==============================================================================
# UI
#==============================================================================

class MyStream(QtCore.QObject):
    """
    this class will emit a signal to write standard output to the UI
    """
    message = QtCore.pyqtSignal(str)
    def __init__(self, parent=None):
        super(MyStream, self).__init__(parent)

    def write(self, message):
        self.message.emit(str(message))

class EDI_Editor_Window(QtGui.QMainWindow):
    """
    This is the main window for editing an edi file.
    
    Includes:
        * Editing points by removing them
        * Adjusting for static shift
        * Removing distortion
        * Rotations
        * Strike estimations
    """
    
    def __init__(self):
        super(EDI_Editor_Window, self).__init__()
        
        
    def ui_setup(self):
        """
        set up the user interface
        """
        
        self.setWindowTitle('EDI Editor')
#        self.resize(1920, 1080)
        self.setWindowState(QtCore.Qt.WindowMaximized)
        
        self.plot_widget = PlotWidget()
        self.centralWidget = self.setCentralWidget(self.plot_widget)
        
        self.menu_file = self.menuBar().addMenu("&File")
        
        self.action_open_file = self.menu_file.addAction("&Open")
        self.action_open_file.triggered.connect(self.get_edi_file)
        
        self.action_close_file = self.menu_file.addAction("C&lose")
        self.action_close_file.triggered.connect(self.close_edi_file)
        
        self.action_save_file = self.menu_file.addAction("&Save")
        self.action_save_file.triggered.connect(self.save_edi_file)
        
        self.menu_plot_properties = self.menuBar().addMenu("Plot Properties")
        self.action_edit_plot = self.menu_plot_properties.addAction("Edit")
        self.action_edit_plot.triggered.connect(self.edit_plot_properties)
        
        self.menu_metadata = self.menuBar().addMenu("Metadata")
        self.action_edit_metadata = self.menu_metadata.addAction("Edit")
        self.action_edit_metadata.triggered.connect(self.edit_metadata)
        
        
        self.my_stream = MyStream()
        self.my_stream.message.connect(self.plot_widget.normal_output)
        
        sys.stdout = self.my_stream
        
        QtCore.QMetaObject.connectSlotsByName(self)
        
    def get_edi_file(self):
        """
        get edi file
        """
        
        print '='*35
        fn_dialog = QtGui.QFileDialog()
        fn = str(fn_dialog.getOpenFileName(caption='Choose EDI file',
                                           directory=self.plot_widget.dir_path,
                                           filter='*.edi'))
                                           
        self.plot_widget.dir_path = os.path.dirname(fn)
                                           
        self.plot_widget.mt_obj = mt.MT(fn)
        self.plot_widget._mt_obj = copy.deepcopy(self.plot_widget.mt_obj)
        self.plot_widget.fill_metadata()
        self.plot_widget.reset_parameters()
        self.plot_widget.plot_properties = PlotSettings(None)
        self.plot_widget.plot()

    def close_edi_file(self):
        pass

    def save_edi_file(self):
        save_fn_dialog = QtGui.QFileDialog()
        save_fn = str(save_fn_dialog.getSaveFileName(caption='Choose EDI File',
                                                     directory=self.plot_widget.dir_path,
                                                     filter='*.edi'))
        
        self.plot_widget.mt_obj.write_edi_file(new_fn=save_fn)
    
    def edit_plot_properties(self):
        self.plot_widget.plot_properties.setup_ui()
        self.plot_widget.plot_properties.show()
        self.plot_widget.plot_properties.settings_updated.connect(self.update_plot)
        
    def update_plot(self):
        
        self.plot_widget.redraw_plot()
    
    def edit_metadata(self):
        self.edi_text_editor = EDITextEditor(self.plot_widget.mt_obj.edi_object)
        self.edi_text_editor.metadata_updated.connect(self.update_edi_metadata)
        
    def update_edi_metadata(self):
        self.plot_widget.mt_obj.edi_object = copy.deepcopy(self.edi_text_editor.edi_obj)      
        self.plot_widget.mt_obj.station = self.plot_widget.mt_obj.edi_object.station         
        self.plot_widget.mt_obj.elev = self.plot_widget.mt_obj.edi_object.elev         
        self.plot_widget.mt_obj.lat = self.plot_widget.mt_obj.edi_object.lat         
        self.plot_widget.mt_obj.lon = self.plot_widget.mt_obj.edi_object.lon         
        self.plot_widget.fill_metadata()        
                       
#==============================================================================
# Plot Widget     
#==============================================================================
class PlotWidget(QtGui.QWidget):
    """
    matplotlib plot of the data
    
    """
    
    def __init__(self):
        super(PlotWidget, self).__init__()

        self.mt_obj = mt.MT()
        self._mt_obj = mt.MT()
        self.static_shift_x = 1.0
        self.static_shift_y = 1.0
        self.rotate_z_angle = 0
        self.rotate_tip_angle = 0
        self.plot_properties = PlotSettings(None)
        self._edited_ss = False
        self._edited_dist = False
        self._edited_rot = False
        self._edited_mask = False
        self.dir_path = os.getcwd()
        
        self.interp_period_min = .001
        self.interp_period_max = 1000.
        self.interp_period_num = 24
        
        self.setup_ui()
        
        
    def setup_ui(self):
        """
        set up the ui
        """
        self.figure = Figure(dpi=150)
        self.mpl_widget = FigureCanvas(self.figure)
        self.mpl_widget.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.mpl_widget.setFocus()
        
        # this will set the minimum width of the mpl plot, important to 
        # resize everything
        screen = QtGui.QDesktopWidget().screenGeometry()
        self.mpl_widget.setMinimumWidth(screen.width()*(1600./1920))
        
        # be able to edit the data
        self.mpl_widget.mpl_connect('pick_event', self.on_pick)
        self.mpl_widget.mpl_connect('axes_enter_event', self.in_axes)
        self.mpl_widget.setSizePolicy(QtGui.QSizePolicy.Expanding,
                                      QtGui.QSizePolicy.Expanding)

        self.mpl_toolbar = NavigationToolbar(self.mpl_widget, self)
        
         # header label font
        header_font = QtGui.QFont()
        header_font.setBold = True
        header_font.setPointSize (16)
        
        # output box for all notes from the program
        self.output_label = QtGui.QLabel("Output")
        self.output_label.setFont(header_font)
        self.output_box = QtGui.QTextEdit()
    
        ## --> SET METADATA
        self.metadata_label = QtGui.QLabel('Metadata')
        self.metadata_label.setFont(header_font)
    
        self.meta_station_name_label = QtGui.QLabel("Station")
        self.meta_station_name_edit = QtGui.QLineEdit(str(self.mt_obj.station))
        self.meta_station_name_edit.editingFinished.connect(self.meta_edit_station)
        
        # sets up with an empty mt object so we can set values to 0
        # once a edi is read in then the metadata will be filled.
        self.meta_lat_label = QtGui.QLabel("Lat (deg)")
        self.meta_lat_edit = QtGui.QLineEdit('{0:.6f}'.format(0.0))
        self.meta_lat_edit.editingFinished.connect(self.meta_edit_lat)
        
        self.meta_lon_label = QtGui.QLabel("Long (deg)")
        self.meta_lon_edit = QtGui.QLineEdit('{0:.6f}'.format(0.0))
        self.meta_lon_edit.editingFinished.connect(self.meta_edit_lon)
        
        self.meta_elev_label = QtGui.QLabel("Elev (m)")
        self.meta_elev_edit = QtGui.QLineEdit('{0:.3f}'.format(0.0))
        self.meta_elev_edit.editingFinished.connect(self.meta_edit_elev)
        
        self.meta_loc_label = QtGui.QLabel("Location")
        self.meta_loc_edit = QtGui.QLineEdit("None")
        self.meta_loc_edit.editingFinished.connect(self.meta_edit_loc)
        
        self.meta_date_label = QtGui.QLabel("Date Acq")
        self.meta_date_edit = QtGui.QLineEdit("YYYY-MM-DD")
        self.meta_date_edit.editingFinished.connect(self.meta_edit_date)
        
        self.meta_acq_label = QtGui.QLabel("Acquired By")
        self.meta_acq_edit = QtGui.QLineEdit("None")
        self.meta_acq_edit.editingFinished.connect(self.meta_edit_acq)
        
        ## Static Shift
        self.static_shift_label = QtGui.QLabel("Static Shift")
        self.static_shift_label.setFont(header_font)
        
        self.static_shift_x_label = QtGui.QLabel("X")
        self.static_shift_x_edit = QtGui.QLineEdit("{0:.4g}".format(self.static_shift_x))
        self.static_shift_x_edit.editingFinished.connect(self.static_shift_set_x)
        
        self.static_shift_y_label = QtGui.QLabel("Y")
        self.static_shift_y_edit = QtGui.QLineEdit("{0:.4g}".format(self.static_shift_y))
        self.static_shift_y_edit.editingFinished.connect(self.static_shift_set_y)
        
        self.static_shift_apply_button = QtGui.QPushButton()
        self.static_shift_apply_button.setText("Apply")
        self.static_shift_apply_button.pressed.connect(self.static_shift_apply)
        
        ## remove distortion 
        self.remove_distortion_label = QtGui.QLabel("Remove Distortion")
        self.remove_distortion_label.setFont(header_font)
        
        self.remove_distortion_button = QtGui.QPushButton()
        self.remove_distortion_button.setText("Remove Distortion [Bibby et al., 2005]")
        self.remove_distortion_button.pressed.connect(self.remove_distortion_apply)
        
        ## rotate data
        self.rotate_data_label = QtGui.QLabel("Rotate")
        self.rotate_data_label.setFont(header_font)

        self.rotate_explanation = QtGui.QLabel("Always rotating original data, assuming: N = 0, E = 90.")
        self.rotate_angle_z_label = QtGui.QLabel("Rotate Z (deg)")
        self.rotate_angle_z_edit = QtGui.QLineEdit("{0:.4g}".format(self.rotate_z_angle))
        self.rotate_angle_z_edit.editingFinished.connect(self.rotate_set_z_angle) 
        
        self.rotate_angle_t_label = QtGui.QLabel("Rotate Tipper (deg)")
        self.rotate_angle_t_edit = QtGui.QLineEdit("{0:.4g}".format(self.rotate_tip_angle))
        self.rotate_angle_t_edit.editingFinished.connect(self.rotate_set_t_angle)        
        
        self.rotate_angle_button = QtGui.QPushButton("Apply")
        self.rotate_angle_button.pressed.connect(self.rotate_data_apply)
        
        self.rotate_estimate_strike_button = QtGui.QPushButton("Estimate Strike")
        self.rotate_estimate_strike_button.pressed.connect(self.rotate_estimate_strike)
        
        
        ## interpolate data 
        self.interp_label = QtGui.QLabel("Interpolate Periods")
        self.interp_label.setFont(header_font)
        
        self.interp_apply_button = QtGui.QPushButton()
        self.interp_apply_button.setText("Apply")
        self.interp_apply_button.pressed.connect(self.interp_apply)        
        
        self.interp_min_label = QtGui.QLabel("Min")
        self.interp_min_edit = QtGui.QLineEdit("{0:.4e}".format(self.interp_period_min))
        self.interp_min_edit.editingFinished.connect(self.interp_set_min)
        
        self.interp_max_label = QtGui.QLabel("Max")
        self.interp_max_edit = QtGui.QLineEdit("{0:.4e}".format(self.interp_period_max))
        self.interp_max_edit.editingFinished.connect(self.interp_set_max)
        
        self.interp_num_label = QtGui.QLabel("Num")
        self.interp_num_edit = QtGui.QLineEdit("{0:.0f}".format(self.interp_period_num))
        self.interp_num_edit.editingFinished.connect(self.interp_set_num)
        
        ## tools label
        self.tools_label = QtGui.QLabel("Tools")
        self.tools_label.setFont(header_font)
       
        ## apply edits button
        self.edits_apply_button = QtGui.QPushButton()
        self.edits_apply_button.setText("Apply Edits")
        self.edits_apply_button.pressed.connect(self.edits_apply)
       
        ## revert back to original data 
        self.revert_button = QtGui.QPushButton()
        self.revert_button.setText("Revert back to orginal data")
        self.revert_button.pressed.connect(self.revert_back)
        
        ## save edits button
        self.save_edits_button = QtGui.QPushButton()
        self.save_edits_button.setText('Save Edits to new EDI file')
        self.save_edits_button.pressed.connect(self.save_edi_file)
        
        ## horizontal line
        h_line_01 = QtGui.QFrame(self)
        h_line_01.setFrameShape(QtGui.QFrame.HLine)
        h_line_01.setFrameShadow(QtGui.QFrame.Sunken)
        
        h_line_02 = QtGui.QFrame(self)
        h_line_02.setFrameShape(QtGui.QFrame.HLine)
        h_line_02.setFrameShadow(QtGui.QFrame.Sunken)
        
        h_line_03 = QtGui.QFrame(self)
        h_line_03.setFrameShape(QtGui.QFrame.HLine)
        h_line_03.setFrameShadow(QtGui.QFrame.Sunken)
        
        h_line_04 = QtGui.QFrame(self)
        h_line_04.setFrameShape(QtGui.QFrame.HLine)
        h_line_04.setFrameShadow(QtGui.QFrame.Sunken)
        
        h_line_05 = QtGui.QFrame(self)
        h_line_05.setFrameShape(QtGui.QFrame.HLine)
        h_line_05.setFrameShadow(QtGui.QFrame.Sunken)
        
        ## vertical spacer
        v_space = QtGui.QSpacerItem(20, 20, 
                                    QtGui.QSizePolicy.Minimum,
                                    QtGui.QSizePolicy.Maximum)
        ###--> layout ---------------------------------------------
        ## mpl plot --> right panel
        mpl_vbox = QtGui.QVBoxLayout()
        mpl_vbox.addWidget(self.mpl_toolbar)
        mpl_vbox.addWidget(self.mpl_widget)        
        
        ##--> Left Panel
        ## Metadata grid
        meta_layout = QtGui.QGridLayout()
       
        meta_layout.addWidget(self.metadata_label, 0, 0)
        meta_layout.addWidget(self.meta_station_name_label, 1, 0)
        meta_layout.addWidget(self.meta_station_name_edit, 1, 1)
        meta_layout.addWidget(self.meta_lat_label, 2, 0)
        meta_layout.addWidget(self.meta_lat_edit, 2, 1)
        meta_layout.addWidget(self.meta_lon_label, 3, 0)
        meta_layout.addWidget(self.meta_lon_edit, 3, 1)
        meta_layout.addWidget(self.meta_elev_label, 4, 0)
        meta_layout.addWidget(self.meta_elev_edit, 4, 1)
        meta_layout.addWidget(self.meta_loc_label, 5, 0)
        meta_layout.addWidget(self.meta_loc_edit, 5, 1)
        meta_layout.addWidget(self.meta_date_label, 6, 0)
        meta_layout.addWidget(self.meta_date_edit, 6, 1)
        meta_layout.addWidget(self.meta_acq_label, 7, 0)
        meta_layout.addWidget(self.meta_acq_edit, 7, 1)
        
        ## static shift
        ss_layout = QtGui.QGridLayout()
        ss_layout.addWidget(self.static_shift_label, 0, 0, 1, 2)
        ss_layout.addWidget(self.static_shift_apply_button, 0, 2, 1, 2)
        ss_layout.addWidget(self.static_shift_x_label, 1, 0)
        ss_layout.addWidget(self.static_shift_x_edit, 1, 1)        
        ss_layout.addWidget(self.static_shift_y_label, 1, 2)
        ss_layout.addWidget(self.static_shift_y_edit, 1, 3) 
        
        ## rotation
        rot_layout = QtGui.QGridLayout()
        rot_layout.addWidget(self.rotate_data_label, 0, 0)
        rot_layout.addWidget(self.rotate_angle_button, 0, 1)
        rot_layout.addWidget(self.rotate_explanation, 1, 0, 1, 2)
        rot_layout.addWidget(self.rotate_angle_z_label, 2, 0)
        rot_layout.addWidget(self.rotate_angle_z_edit, 2, 1)
        rot_layout.addWidget(self.rotate_angle_t_label, 3, 0)
        rot_layout.addWidget(self.rotate_angle_t_edit, 3, 1)
        rot_layout.addWidget(self.rotate_estimate_strike_button, 4, 0, 1, 2)
        
        ## interpolate 
        interp_layout = QtGui.QGridLayout()
        interp_layout.addWidget(self.interp_label, 0, 0)
        interp_layout.addWidget(self.interp_apply_button, 0, 1)
        interp_layout.addWidget(self.interp_min_label, 1, 0)
        interp_layout.addWidget(self.interp_min_edit, 1, 1)
        interp_layout.addWidget(self.interp_max_label, 2, 0)
        interp_layout.addWidget(self.interp_max_edit, 2, 1)
        interp_layout.addWidget(self.interp_num_label, 3, 0)
        interp_layout.addWidget(self.interp_num_edit, 3, 1)
        
        ## left panel
        info_layout = QtGui.QVBoxLayout()
        info_layout.addLayout(meta_layout)

        info_layout.addWidget(h_line_01)
        info_layout.addWidget(self.remove_distortion_label)
        info_layout.addWidget(self.remove_distortion_button)
        info_layout.addWidget(h_line_02)
        info_layout.addLayout(ss_layout)
        info_layout.addWidget(h_line_03)
        info_layout.addLayout(rot_layout)
        info_layout.addWidget(h_line_04)
        info_layout.addLayout(interp_layout)
        info_layout.addWidget(h_line_05)
        info_layout.addWidget(self.tools_label)
        info_layout.addWidget(self.edits_apply_button)
        info_layout.addWidget(self.revert_button)
        info_layout.addWidget(self.save_edits_button)
        info_layout.addItem(v_space)
        info_layout.addWidget(self.output_label)
        info_layout.addWidget(self.output_box)
            
        ## final layout
        final_layout = QtGui.QHBoxLayout()
        final_layout.addLayout(info_layout)
        final_layout.addLayout(mpl_vbox )

        
        self.setLayout(final_layout)
        self.mpl_widget.updateGeometry()
        
    def meta_edit_station(self):
        self.mt_obj.station = str(self.meta_station_name_edit.text())
        
    def meta_edit_lat(self):
        self.mt_obj.lat = float(str(self.meta_lat_edit.text()))
        self.meta_lat_edit.setText('{0:.6f}'.format(self.mt_obj.lat))
        
    def meta_edit_lon(self):
        self.mt_obj.lon = float(str(self.meta_lat_edit.text()))
        self.meta_lon_edit.setText('{0:.6f}'.format(self.mt_obj.lat))
        
    def meta_edit_elev(self):
        self.mt_obj.elev = float(str(self.meta_elev_edit.text()))
        self.meta_elev_edit.setText('{0:.6f}'.format(self.mt_obj.elev))
        
    def meta_edit_loc(self):
        self.mt_obj.edi_object.Header.loc = (str(self.meta_loc_edit.text()))
        self.meta_loc_edit.setText('{0}'.format(self.mt_obj.edi_object.Header.loc))
        
    def meta_edit_date(self):
        self.mt_obj.edi_object.Header.filedate = str(self.meta_date_edit.text())
        self.meta_date_edit.setText(self.mt_obj.edi_object.Header.filedate) 
    
    def meta_edit_acq(self):
        self.mt_obj.edi_object.Header.acqby = str(self.meta_acq_edit.text())
        self.meta_acq_edit.setText(self.mt_obj.edi_object.Header.acqby)    
   
    def fill_metadata(self):
        self.meta_station_name_edit.setText(self.mt_obj.station)
        self.meta_lat_edit.setText('{0:.6f}'.format(self.mt_obj.lat))
        self.meta_lon_edit.setText('{0:.6f}'.format(self.mt_obj.lon))
        self.meta_elev_edit.setText('{0:.6f}'.format(self.mt_obj.elev))
        self.meta_date_edit.setText('{0}'.format(self.mt_obj.edi_object.Header.filedate))
        self.meta_loc_edit.setText('{0}'.format(self.mt_obj.edi_object.Header.loc))
        self.meta_acq_edit.setText('{0}'.format(self.mt_obj.edi_object.Header.acqby))
        
    def static_shift_set_x(self):
        self.static_shift_x = float(str(self.static_shift_x_edit.text()))
        self.static_shift_x_edit.setText('{0:.4f}'.format(self.static_shift_x))
        
    def static_shift_set_y(self):
        self.static_shift_y = float(str(self.static_shift_y_edit.text()))
        self.static_shift_y_edit.setText('{0:.4f}'.format(self.static_shift_y))
     
    def static_shift_apply(self):
        """
        shift apparent resistivity up or down
        """
        if self._edited_dist == False and self._edited_rot == False and \
           self._edited_mask == False:
            # be sure to apply the static shift to the original data
            new_z_obj = self._mt_obj.remove_static_shift(ss_x=self.static_shift_x,
                                                         ss_y=self.static_shift_y)
            # print the static shift applied 
            print "\n    Static shift applied to original data:"
        else:
            new_z_obj = self.mt_obj.remove_static_shift(ss_x=self.static_shift_x,
                                                        ss_y=self.static_shift_y)
            # print the static shift applied 
            print "\n    - Static shift applied to edited data:"
        
        # print the static shift applied
        print "        x = {0:.4f}, y = {1:.4f}".format(self.static_shift_x,
                                                        self.static_shift_y)          
        self._edited_ss = True
                                                
        self.mt_obj.Z = new_z_obj
        self.redraw_plot()
        
    def remove_distortion_apply(self):
        """
        remove distortion from the mt repsonse
        """
        if self._edited_dist == False and self._edited_rot == False and \
           self._edited_mask == False:
            # remove distortion from original data
            distortion, new_z_object = self._mt_obj.remove_distortion()
            print '\n    - Removed distortion from original data'
             
        else:
            # remove distortion from edited data
            distortion, new_z_object = self.mt_obj.remove_distortion()
            print '\n    - Removed distortion from edited data'

        self._edited_dist = True
        self.mt_obj.Z = new_z_object

        print '       Distortion matrix:'
        print '          | {0:+.3f}  {1:+.3f} |'.format(distortion[0, 0],
                                                        distortion[0, 1])
        print '          | {0:+.3f}  {1:+.3f} |'.format(distortion[1, 0],
                                                        distortion[1, 1]) 
        
        self.redraw_plot()
        
    def rotate_set_z_angle(self):
        """
        set z rotation angle
        
        Always rotate original data otherwiswe can get messy
        """
        self.rotate_z_angle = float(str(self.rotate_angle_z_edit.text()))
        self.rotate_angle_z_edit.setText("{0:.4f}".format(self.rotate_z_angle))
        
        self.rotate_tip_angle = float(self.rotate_z_angle)
        self.rotate_angle_t_edit.setText("{0:.4f}".format(self.rotate_tip_angle))

                                                         
    def rotate_set_t_angle(self):
        """
        rotate tipper data assuming North is 0 and E is 90
        
        Always rotate original data otherwiswe can get messy
        """
        self.rotate_tip_angle = float(str(self.rotate_angle_t_edit.text()))
        self.rotate_angle_t_edit.setText("{0:.4f}".format(self.rotate_tip_angle))

    def rotate_data_apply(self):
        """
        rotate both Z and tipper original data by the input angles
        """
        
        rot_z_obj = copy.deepcopy(self._mt_obj.Z)
        rot_z_obj.rotate(self.rotate_z_angle)
        
        self.mt_obj.Z = rot_z_obj
        
        rot_t_obj = copy.deepcopy(self._mt_obj.Tipper)
        rot_t_obj.rotate(self.rotate_tip_angle)
        
        self.mt_obj.Tipper = rot_t_obj
        
        if self._edited_ss == True:
            self.static_shift_apply()
        
        if self._edited_dist == True:
            self.remove_distortion_apply()
        
        self.redraw_plot()
        
        self._edited_rot = True
        
        print '\n   Rotated orginal data clockwise by:'
        print '      Z = {0:.3g}'.format(self.rotate_z_angle)
        print '      T = {0:.3g}'.format(self.rotate_tip_angle)
        
    def rotate_estimate_strike(self):
        """
        estimate strike from the invariants, phase tensor, and tipper if 
        measured.
        """
        z_list = [copy.deepcopy(self.mt_obj.Z)]
        t_list = [copy.deepcopy(self.mt_obj.Tipper)]
        strike_plot = plotstrike2d.PlotStrike2D(z_object_list=z_list,
                                                tipper_object_list=t_list,
                                                plot_yn='n')
        strike_plot.plot_type = 1
        if np.any(self.mt_obj.Tipper.tipper == 0) == True:
            strike_plot.plot_tipper = 'n'
        elif np.any(self.mt_obj.Tipper.tipper == 0) == False:
            strike_plot.plot_tipper = 'y'
            
        strike_plot.fold = False
        strike_plot.plot_range = 'data'
        strike_plot.plot()
        
    def interp_set_min(self):
        self.interp_period_min = float(str(self.interp_min_edit.text()))
        self.interp_min_edit.setText('{0:.4e}'.format(self.interp_period_min))
        
    def interp_set_max(self):
        self.interp_period_max = float(str(self.interp_max_edit.text()))
        self.interp_max_edit.setText('{0:.4e}'.format(self.interp_period_max))
    
    def interp_set_num(self):
        self.interp_period_num = int(str(self.interp_num_edit.text()))
        self.interp_num_edit.setText('{0:.0f}'.format(self.interp_period_num))
        
    def interp_apply(self):
        """
        interpolate data on to a new period list that is equally spaced in 
        log space.
        """
        
        new_period = np.logspace(np.log10(self.interp_period_min),
                                 np.log10(self.interp_period_max),
                                 num=self.interp_period_num)
                                 
        if self._edited_dist == True or self._edited_mask == True or \
           self._edited_rot == True or self._edited_ss == True:
            new_z, new_tip = self.mt_obj.interpolate(1./new_period)
            self.mt_obj.Z = new_z
            self.mt_obj.Tipper = new_tip
            
        else:
            new_z, new_tip = self._mt_obj.interpolate(1./new_period)
            self.mt_obj.Z = new_z
            self.mt_obj.Tipper = new_tip
            
        self.redraw_plot()
        
        print 'Interpolated data onto periods:'
        for ff in new_period:
            print '    {0:.6e}'.format(ff)
        
        
    def edits_apply(self):
        """
        apply edits, well edits are already made, but replot without edited
        points
        """
        
        self.redraw_plot()
           
          
    def revert_back(self):
        """
        revert back to original data
        
        """
        
        self.mt_obj = copy.deepcopy(self._mt_obj)
        self.reset_parameters()
        self.redraw_plot()
        
        print '\n'        
        print '-'*35
        print "Reverted back to original input data."
        print "Reset editing parameters."
        
    def reset_parameters(self):
        self.static_shift_x = 1.0
        self.static_shift_y = 1.0
        self.static_shift_x_edit.setText("{0:.4g}".format(self.static_shift_x))
        self.static_shift_y_edit.setText("{0:.4g}".format(self.static_shift_y))
        self.rotate_z_angle = 0.0
        self.rotate_tip_angle = 0.0
        self.rotate_angle_z_edit.setText("{0:.4g}".format(self.rotate_z_angle))
        self.rotate_angle_t_edit.setText("{0:.4g}".format(self.rotate_tip_angle))
        
        self._edited_ss = False
        self._edited_dist = False
        self._edited_rot = False
        
    def save_edi_file(self):
        """
        save edited edi file to the chosen file name.
        """
        
        save_dialog = QtGui.QFileDialog()
        save_fn = str(save_dialog.getSaveFileName(caption='Choose EDI file',
                                                  directory=self.dir_path,
                                                  filter='*.edi'))
        self.mt_obj.write_edi_file(new_fn=save_fn)
        
    @QtCore.pyqtSlot(str)
    def normal_output(self, message):
        self.output_box.moveCursor(QtGui.QTextCursor.End)
        self.output_box.insertPlainText(message)
        
    def plot(self):
        """
        plot the response
        
        will have original data below the editable data
        """
        
        self.figure.clf()
        
        self.figure.suptitle(self.mt_obj.station, 
                             fontdict={'size':self.plot_properties.fs+4,
                                       'weight':'bold'})
        
        # make some useful internal variabls
        font_dict = {'size':self.plot_properties.fs+2, 'weight':'bold'}
        plot_period = 1./self.mt_obj.Z.freq
        plot_period_o = 1./self._mt_obj.Z.freq
            
        if np.all(self.mt_obj.Tipper.tipper == 0) == True:
                print 'No Tipper data for station {0}'.format(self.mt_obj.station)
                self.plot_tipper = False
        else:
            self.plot_tipper = True
            
        #set x-axis limits from short period to long period
        self.plot_properties.xlimits = (10**(np.floor(np.log10(plot_period_o.min()))),
                                        10**(np.ceil(np.log10((plot_period_o.max())))))
        
        #--> make key word dictionaries for plotting
        kw_xx = {'color':self.plot_properties.cted,
                 'marker':self.plot_properties.mted,
                 'ms':self.plot_properties.ms,
                 'ls':':',
                 'lw':self.plot_properties.lw,
                 'e_capsize':self.plot_properties.e_capsize,
                 'e_capthick':self.plot_properties.e_capthick,
                 'picker':3}        
       
        kw_yy = {'color':self.plot_properties.ctmd,
                 'marker':self.plot_properties.mtmd,
                 'ms':self.plot_properties.ms,
                 'ls':':',
                 'lw':self.plot_properties.lw,
                 'e_capsize':self.plot_properties.e_capsize,
                 'e_capthick':self.plot_properties.e_capthick,
                 'picker':3} 
                 
        kw_xx_o = {'color':self.plot_properties.cteo,
                   'marker':self.plot_properties.mted,
                   'ms':self.plot_properties.ms,
                   'ls':':',
                   'lw':self.plot_properties.lw,
                   'e_capsize':self.plot_properties.e_capsize,
                   'e_capthick':self.plot_properties.e_capthick,
                   'picker':None}        
       
        kw_yy_o = {'color':self.plot_properties.ctmo,
                   'marker':self.plot_properties.mtmd,
                   'ms':self.plot_properties.ms,
                   'ls':':',
                   'lw':self.plot_properties.lw,
                   'e_capsize':self.plot_properties.e_capsize,
                   'e_capthick':self.plot_properties.e_capthick,
                   'picker':None} 
        
        # create a grid of subplots
        gs = gridspec.GridSpec(3, 2, height_ratios=[2, 1.5, 1])
        
        gs.update(hspace=self.plot_properties.subplot_hspace,
                  wspace=self.plot_properties.subplot_wspace,
                  left=self.plot_properties.subplot_left,
                  right=self.plot_properties.subplot_right,
                  top=self.plot_properties.subplot_top,
                  bottom=self.plot_properties.subplot_bottom)
                  
        #find locations where points have been masked
        nzxx = np.nonzero(self.mt_obj.Z.z[:, 0, 0])[0]
        nzxy = np.nonzero(self.mt_obj.Z.z[:, 0, 1])[0]
        nzyx = np.nonzero(self.mt_obj.Z.z[:, 1, 0])[0]
        nzyy = np.nonzero(self.mt_obj.Z.z[:, 1, 1])[0]
        
        nzxx_o = np.nonzero(self._mt_obj.Z.z[:, 0, 0])[0]
        nzxy_o = np.nonzero(self._mt_obj.Z.z[:, 0, 1])[0]
        nzyx_o = np.nonzero(self._mt_obj.Z.z[:, 1, 0])[0]
        nzyy_o = np.nonzero(self._mt_obj.Z.z[:, 1, 1])[0]
                  
        # make axis od = off-diagonal, d = diagonal, share x axis across plots
        self.ax_res_od = self.figure.add_subplot(gs[0, 0])
        self.ax_res_d = self.figure.add_subplot(gs[0, 1], 
                                                sharex=self.ax_res_od)

        self.ax_phase_od = self.figure.add_subplot(gs[1, 0], 
                                                sharex=self.ax_res_od)
        self.ax_phase_d = self.figure.add_subplot(gs[1, 1], 
                                                sharex=self.ax_res_od)
        
        # include tipper, r = real, i = imaginary
        self.ax_tip_x = self.figure.add_subplot(gs[2, 0], 
                                                sharex=self.ax_res_od)
        self.ax_tip_y = self.figure.add_subplot(gs[2, 1],
                                                sharex=self.ax_res_od)
        
        self.ax_list = [self.ax_res_od, self.ax_res_d,
                        self.ax_phase_od, self.ax_phase_d,
                        self.ax_tip_x, self.ax_tip_y]
        
        ## --> plot apparent resistivity, phase and tipper
        ## plot orginal apparent resistivity
        if self.plot_properties.plot_original_data == True:                                 
            orxx = mtplt.plot_errorbar(self.ax_res_d, 
                                       plot_period_o[nzxx_o],
                                       self._mt_obj.Z.resistivity[nzxx_o, 0, 0],
                                       self._mt_obj.Z.resistivity_err[nzxx_o, 0, 0],
                                       **kw_xx_o)
            orxy = mtplt.plot_errorbar(self.ax_res_od, 
                                       plot_period_o[nzxy_o],
                                       self._mt_obj.Z.resistivity[nzxy_o, 0, 1],
                                       self._mt_obj.Z.resistivity_err[nzxy_o, 0, 1],
                                       **kw_xx_o)
            oryx = mtplt.plot_errorbar(self.ax_res_od, 
                                       plot_period_o[nzyx_o],
                                       self._mt_obj.Z.resistivity[nzyx_o, 1, 0],
                                       self._mt_obj.Z.resistivity_err[nzyx_o, 1, 0],
                                       **kw_yy_o)
            oryy = mtplt.plot_errorbar(self.ax_res_d, 
                                       plot_period_o[nzyy_o],
                                       self._mt_obj.Z.resistivity[nzyy_o, 1, 1],
                                       self._mt_obj.Z.resistivity_err[nzyy_o, 1, 1],
                                       **kw_yy_o)
            # plot original phase                                 
            epxx = mtplt.plot_errorbar(self.ax_phase_d, 
                                       plot_period_o[nzxx_o],
                                       self._mt_obj.Z.phase[nzxx_o, 0, 0],
                                       self._mt_obj.Z.phase_err[nzxx_o, 0, 0],
                                       **kw_xx_o)
            epxy = mtplt.plot_errorbar(self.ax_phase_od, 
                                       plot_period_o[nzxy_o],
                                       self._mt_obj.Z.phase[nzxy_o, 0, 1],
                                       self._mt_obj.Z.phase_err[nzxy_o, 0, 1],
                                       **kw_xx_o)
            epyx = mtplt.plot_errorbar(self.ax_phase_od, 
                                       plot_period_o[nzyx_o],
                                       self._mt_obj.Z.phase[nzyx_o, 1, 0]+180,
                                       self._mt_obj.Z.phase_err[nzyx_o, 1, 0],
                                       **kw_yy_o)
            epyy = mtplt.plot_errorbar(self.ax_phase_d, 
                                       plot_period_o[nzyy_o],
                                       self._mt_obj.Z.phase[nzyy_o, 1, 1],
                                       self._mt_obj.Z.phase_err[nzyy_o, 1, 1],
                                       **kw_yy_o)
                                         
        # plot manipulated data apparent resistivity
        erxx = mtplt.plot_errorbar(self.ax_res_d, 
                                   plot_period[nzxx],
                                   self.mt_obj.Z.resistivity[nzxx, 0, 0],
                                   self.mt_obj.Z.resistivity_err[nzxx, 0, 0],
                                   **kw_xx)
        erxy = mtplt.plot_errorbar(self.ax_res_od, 
                                   plot_period[nzxy],
                                   self.mt_obj.Z.resistivity[nzxy, 0, 1],
                                   self.mt_obj.Z.resistivity_err[nzxy, 0, 1],
                                   **kw_xx)
        eryx = mtplt.plot_errorbar(self.ax_res_od, 
                                   plot_period[nzyx],
                                   self.mt_obj.Z.resistivity[nzyx, 1, 0],
                                   self.mt_obj.Z.resistivity_err[nzyx, 1, 0],
                                   **kw_yy)
        eryy = mtplt.plot_errorbar(self.ax_res_d, 
                                   plot_period[nzyy],
                                   self.mt_obj.Z.resistivity[nzyy, 1, 1],
                                   self.mt_obj.Z.resistivity_err[nzyy, 1, 1],
                                   **kw_yy)

                                         
        #--> set axes properties for apparent resistivity
        if self.plot_properties.res_limits_d != None:
            self.ax_res_d.set_ylim(self.plot_properties.res_limits_d)
        if self.plot_properties.res_limits_od != None:
            self.ax_res_od.set_ylim(self.plot_properties.res_limits_od)
        for aa, ax in enumerate([self.ax_res_od, self.ax_res_d]):
            plt.setp(ax.get_xticklabels(), visible=False)
            if aa == 0:            
                ax.set_ylabel('App. Res. ($\mathbf{\Omega \cdot m}$)',
                              fontdict=font_dict)
            ax.set_yscale('log')
            ax.set_xscale('log')
            ax.set_xlim(self.plot_properties.xlimits)

            ax.grid(True, alpha=.25, which='both', color=(.25, .25, .25),
                          lw=.25)
            # make the plot cleaner by removing the bottom x label
            ylim = ax.get_ylim()
            ylimits = (10**np.floor(np.log10(ylim[0])), 
                      10**np.ceil(np.log10(ylim[1])))
            ax.set_ylim(ylimits)
            ylabels = [' ', ' ']+\
                     [mtplt.labeldict[ii] for ii 
                     in np.arange(np.log10(ylimits[0])+1, 
                                  np.log10(ylimits[1])+1, 1)]
            ax.set_yticklabels(ylabels)
            
        self.ax_res_od.legend((erxy[0], eryx[0]), 
                              ('$Z_{xy}$', '$Z_{yx}$'),
                                loc=3, 
                                markerscale=1, 
                                borderaxespad=.01,
                                labelspacing=.07, 
                                handletextpad=.2, 
                                borderpad=.02)
        self.ax_res_d.legend((erxx[0], eryy[0]), 
                              ('$Z_{xx}$', '$Z_{yy}$'),
                                loc=3, 
                                markerscale=1, 
                                borderaxespad=.01,
                                labelspacing=.07, 
                                handletextpad=.2, 
                                borderpad=.02)

        
        ##--> plot phase                           
        # plot manipulated data                         
        epxx = mtplt.plot_errorbar(self.ax_phase_d, 
                                   plot_period[nzxx],
                                   self.mt_obj.Z.phase[nzxx, 0, 0],
                                   self.mt_obj.Z.phase_err[nzxx, 0, 0],
                                   **kw_xx)
        epxy = mtplt.plot_errorbar(self.ax_phase_od, 
                                   plot_period[nzxy],
                                   self.mt_obj.Z.phase[nzxy, 0, 1],
                                   self.mt_obj.Z.phase_err[nzxy, 0, 1],
                                   **kw_xx)
        epyx = mtplt.plot_errorbar(self.ax_phase_od, 
                                   plot_period[nzyx],
                                   self.mt_obj.Z.phase[nzyx, 1, 0]+180,
                                   self.mt_obj.Z.phase_err[nzyx, 1, 0],
                                   **kw_yy)
        epyy = mtplt.plot_errorbar(self.ax_phase_d, 
                                   plot_period[nzyy],
                                   self.mt_obj.Z.phase[nzyy, 1, 1],
                                   self.mt_obj.Z.phase_err[nzyy, 1, 1],
                                   **kw_yy)
        
                                         
        #--> set axes properties
        if self.plot_properties.phase_limits_od != None:
            self.ax_phase_od.set_ylim(self.plot_properties.phase_limits_od)
        if self.plot_properties.phase_limits_d != None:
            self.ax_phase_d.set_ylim(self.plot_properties.phase_limits_d)
        for aa, ax in enumerate([self.ax_phase_od, self.ax_phase_d]):
            ax.set_xlabel('Period (s)', font_dict)
            ax.set_xscale('log')
            if aa == 0:
                ax.set_ylabel('Phase (deg)', font_dict)
                #ax.yaxis.set_major_locator(MultipleLocator(15))
                #ax.yaxis.set_minor_locator(MultipleLocator(5))
            ax.grid(True, alpha=.25, which='both', color=(.25, .25, .25),
                          lw=.25)

        
        # set the last label to be an empty string for easier reading
        for ax in [self.ax_phase_od, self.ax_phase_d]:
            y_labels = ax.get_yticks().tolist()
            y_labels[0] = ''
            ax.set_yticklabels(y_labels)

        ## --> plot tipper                                 
        #set th xaxis tick labels to invisible
        plt.setp(self.ax_phase_od.xaxis.get_ticklabels(), visible=False)
        plt.setp(self.ax_phase_d.xaxis.get_ticklabels(), visible=False)
        self.ax_phase_od.set_xlabel('')
        self.ax_phase_d.set_xlabel('')
        
        # make sure there is tipper data to plot
        if self.plot_tipper == True:
        
            kw_tx = dict(kw_xx)
            kw_ty = dict(kw_yy)
            kw_tx['color'] = self.plot_properties.tipper_x_color
            kw_ty['color'] = self.plot_properties.tipper_y_color
            
            ntx = np.nonzero(self.mt_obj.Tipper.amplitude[:, 0, 0])[0]
            nty = np.nonzero(self.mt_obj.Tipper.amplitude[:, 0, 1])[0]
            ntx_o = np.nonzero(self._mt_obj.Tipper.amplitude[:, 0, 0])[0]
            nty_o = np.nonzero(self._mt_obj.Tipper.amplitude[:, 0, 1])[0]
            
            # plot magnitude of real and imaginary induction vectors
            if self.plot_properties.plot_original_data == True:
                etxo = mtplt.plot_errorbar(self.ax_tip_x,
                                           plot_period_o[ntx_o],
                                           self._mt_obj.Tipper.amplitude[ntx_o, 0, 0],
                                           self._mt_obj.Tipper.amplitude_err[ntx_o, 0, 0],
                                           **kw_xx_o)
                                  
                etyo = mtplt.plot_errorbar(self.ax_tip_y,
                                          plot_period_o[nty_o],
                                          self._mt_obj.Tipper.amplitude[nty_o, 0, 1],
                                          self._mt_obj.Tipper.amplitude_err[nty_o, 0, 1],
                                          **kw_yy_o)
            
            # plot magnitude of edited induction vectors
            etx = mtplt.plot_errorbar(self.ax_tip_x,
                                      plot_period[ntx],
                                      self.mt_obj.Tipper.amplitude[ntx, 0, 0],
                                      self.mt_obj.Tipper.amplitude_err[ntx, 0, 0],
                                      **kw_tx) 
    
            ety = mtplt.plot_errorbar(self.ax_tip_y,
                                      plot_period[nty],
                                      self.mt_obj.Tipper.amplitude[nty, 0, 1],
                                      self.mt_obj.Tipper.amplitude_err[nty, 0, 1],
                                      **kw_ty) 
                                      
            self.ax_tip_x.legend([etx[0]], 
                                  ['|Re{T}|'],
                                    loc=2,
                                    markerscale=1, 
                                    borderaxespad=.01,
                                    handletextpad=.2, 
                                    borderpad=.05)
            self.ax_tip_y.legend([ety[0]], 
                                  ['|Im{T}|'],
                                    loc=2,
                                    markerscale=1, 
                                    borderaxespad=.01,
                                    handletextpad=.2, 
                                    borderpad=.05)
                                            
        #--> set axes properties for magnitude and angle of induction vectors
        if self.plot_properties.tipper_x_limits != None:
            self.ax_tip_x.set_ylim(self.plot_properties.tipper_x_limits)
        if self.plot_properties.tipper_y_limits != None:
            self.ax_tip_y.set_ylim(self.plot_properties.tipper_y_limits)
        for aa, ax in enumerate([self.ax_tip_x, self.ax_tip_y]):
            if aa == 0:            
                ax.set_ylabel('Magnitude', fontdict=font_dict)
            
            ax.set_xscale('log')
            ax.grid(True, alpha=.25, which='both', color=(.25, .25, .25),
                          lw=.25)
  

        
        # set the last label to be an empty string for easier reading
        for ax in [self.ax_tip_x, self.ax_tip_y]:
            y_labels = ax.get_yticks().tolist()
            y_labels[-1] = ''
            ax.set_yticklabels(y_labels)                             
    
        ## --> need to be sure to draw the figure        
        self.mpl_widget.draw()
        
    def redraw_plot(self):
        self.plot()
        
    def on_pick(self, event):
        """
        mask a data point when it is clicked on.  
        """         
        data_point = event.artist
        data_period = data_point.get_xdata()[event.ind]
        data_value = data_point.get_ydata()[event.ind]
        
        mask_kw = {'color' : self.plot_properties.mask_color,
                   'marker' : self.plot_properties.mask_marker,
                   'ms' : self.plot_properties.mask_ms,
                   'mew' : self.plot_properties.mask_mew}
        
        # modify Z
        if event.mouseevent.button == 1:
            self._edited_mask = True
            if self._ax_index == 0 or self._ax_index == 1:
                d_index = np.where(self.mt_obj.Z.resistivity == data_value)
                comp_jj = d_index[1][0]
                comp_kk = d_index[2][0]
                
                # mask point in impedance object
                self.mt_obj.Z.z[d_index] = 0.0+0.0*1j            
                
                self._ax.plot(data_period, data_value, **mask_kw)
                
                # mask phase as well
                if self._ax_index == 0:
                    if comp_jj == 1 and comp_kk == 0:
                        self.ax_phase_od.plot(data_period, 
                                              self.mt_obj.Z.phase[d_index]+180,
                                              **mask_kw)
                    else:
                        self.ax_phase_od.plot(data_period, 
                                              self.mt_obj.Z.phase[d_index],
                                              **mask_kw)
                elif self._ax_index == 1:
                    self.ax_phase_d.plot(data_period, 
                                          self.mt_obj.Z.phase[d_index],
                                          **mask_kw)
                
            # mask phase points
            elif self._ax_index == 2 or self._ax_index == 3:
                try:
                    d_index = np.where(self.mt_obj.Z.phase == data_value)
                except IndexError:
                    d_index = np.where(self.mt_obj.Z.phase == data_value-180)    
                
                # mask point in impedance object
                self.mt_obj.Z.z[d_index] = 0.0+0.0*1j            
                
                # mask the point in the axis selected
                self._ax.plot(data_period, data_value, **mask_kw)
                
                # mask resistivity as well
                if self._ax_index == 2:
                    self.ax_res_od.plot(data_period, 
                                        self.mt_obj.Z.resistivity[d_index],
                                        **mask_kw)
                elif self._ax_index == 3:
                    self.ax_res_d.plot(data_period, 
                                       self.mt_obj.Z.resistivity[d_index],
                                       **mask_kw)
            
            # mask tipper Tx
            elif self._ax_index == 4 or self._ax_index == 5:
                data_value = np.round(data_value, 8)
                d_index = np.where(np.round(self.mt_obj.Tipper.amplitude,
                                            8) == data_value)
                                            
                print d_index
                                            
                # mask point
                self._ax.plot(data_period, data_value, **mask_kw)
                
                # set tipper data to 0
                self.mt_obj.Tipper.tipper[d_index] = 0.0+0.0j
                self.mt_obj.Tipper.tippererr[d_index] = 0.0
                
                self.mt_obj.Tipper._compute_amp_phase()
                
            self._ax.figure.canvas.draw()
                
    def in_axes(self, event):
        """
        check to see which axis the mouse is in
        """
        
        self._ax = event.inaxes
        
        # find the component index so that it can be masked
        for ax_index, ax in enumerate(self.ax_list):
            if ax == event.inaxes:
                self._ax_index = ax_index
        

#==============================================================================
#  Plot setting        
#==============================================================================
class PlotSettings(QtGui.QWidget):
    settings_updated = QtCore.pyqtSignal()
    def __init__(self, parent, **kwargs):
        super(PlotSettings, self).__init__(parent)
        
        self.fs = kwargs.pop('fs', 10)
        self.lw = kwargs.pop('lw', 1.0)
        self.ms = kwargs.pop('ms', 4)
        
        self.e_capthick = kwargs.pop('e_capthick', 1)
        self.e_capsize =  kwargs.pop('e_capsize', 4)

        self.cted = kwargs.pop('cted', (0, 0, .65))
        self.ctmd = kwargs.pop('ctmd', (.65, 0, 0))
        self.cteo = kwargs.pop('cted', (.5, .5, .5))
        self.ctmo = kwargs.pop('ctmd', (.75, .75, .75))
        
        self.mted = kwargs.pop('mted', 's')
        self.mtmd = kwargs.pop('mtmd', 'o')
         
        self.res_limits_od = kwargs.pop('res_limits_od', None)   
        self.res_limits_d = kwargs.pop('res_limits_d', None)   
        
        self._res_limits_od_min = None
        self._res_limits_od_max = None
        self._res_limits_d_min = None
        self._res_limits_d_max = None
        
        self.phase_limits_od = kwargs.pop('phase_limits_od', None)   
        self.phase_limits_d = kwargs.pop('phase_limits_d', None)
        
        self._phase_limits_od_min = None
        self._phase_limits_od_max = None
        self._phase_limits_d_min = None
        self._phase_limits_d_max = None
        
        self.tipper_x_limits = kwargs.pop('tipper_x_limits', None)
        self.tipper_y_limits = kwargs.pop('tipper_y_limits', None)
        
        self._tip_x_limits_min = None
        self._tip_x_limits_max = None
        self._tip_y_limits_min = None
        self._tip_y_limits_max = None

        
        self.subplot_wspace = kwargs.pop('subplot_wspace', .15)
        self.subplot_hspace = kwargs.pop('subplot_hspace', .00)
        self.subplot_right = kwargs.pop('subplot_right', .98)
        self.subplot_left = kwargs.pop('subplot_left', .08)
        self.subplot_top = kwargs.pop('subplot_top', .93)
        self.subplot_bottom = kwargs.pop('subplot_bottom', .08)
        
        self.tipper_x_color = kwargs.pop('tipper_x_color', (.4, 0, .2))
        self.tipper_y_color = kwargs.pop('tipper_y_color',  (0, .9, .9))
        
        self.plot_original_data = kwargs.pop('plot_original_data', True)
        
        self.mask_marker = kwargs.pop('mask_marker', 'x')
        self.mask_ms = kwargs.pop('mask_ms', 10)
        self.mask_mew = kwargs.pop('mask_mew', 3)
        self.mask_color = kwargs.pop('mask_color', 'k')
        
        #self.setup_ui()

    def setup_ui(self):
        """
        setup the user interface
        """        
        
        self.fs_label = QtGui.QLabel("Font Size")
        self.fs_edit = QtGui.QLineEdit("{0:.2f}".format(self.fs))
        self.fs_edit.editingFinished.connect(self.set_fs)
        
        self.lw_label = QtGui.QLabel("Line Width")
        self.lw_edit = QtGui.QLineEdit("{0:.2f}".format(self.lw))
        self.lw_edit.editingFinished.connect(self.set_lw)
        
        self.ms_label = QtGui.QLabel("Marker Size")
        self.ms_edit = QtGui.QLineEdit("{0:.2f}".format(self.ms))
        self.ms_edit.editingFinished.connect(self.set_ms)
        
        self.mted_label = QtGui.QLabel("Marker x components")
        self.mted_combo = QtGui.QComboBox()
        self.mted_combo.addItem(self.mted)
        self.mted_combo.addItem('.')
        self.mted_combo.addItem(',')
        self.mted_combo.addItem('o')
        self.mted_combo.addItem('v')
        self.mted_combo.addItem('^')
        self.mted_combo.addItem('<')
        self.mted_combo.addItem('>')
        self.mted_combo.addItem('s')
        self.mted_combo.addItem('p')
        self.mted_combo.addItem('*')
        self.mted_combo.addItem('h')
        self.mted_combo.addItem('H')
        self.mted_combo.addItem('+')
        self.mted_combo.addItem('x')
        self.mted_combo.addItem('D')
        self.mted_combo.addItem('d')
        self.mted_combo.addItem('|')
        self.mted_combo.addItem('_')
        self.mted_combo.activated[str].connect(self.set_mted)
        
        self.mtmd_label = QtGui.QLabel("Marker y components")
        self.mtmd_combo = QtGui.QComboBox()
        self.mtmd_combo.addItem(self.mtmd)
        self.mtmd_combo.addItem('.')
        self.mtmd_combo.addItem(',')
        self.mtmd_combo.addItem('o')
        self.mtmd_combo.addItem('v')
        self.mtmd_combo.addItem('^')
        self.mtmd_combo.addItem('<')
        self.mtmd_combo.addItem('>')
        self.mtmd_combo.addItem('s')
        self.mtmd_combo.addItem('p')
        self.mtmd_combo.addItem('*')
        self.mtmd_combo.addItem('h')
        self.mtmd_combo.addItem('H')
        self.mtmd_combo.addItem('+')
        self.mtmd_combo.addItem('x')
        self.mtmd_combo.addItem('D')
        self.mtmd_combo.addItem('d')
        self.mtmd_combo.addItem('|')
        self.mtmd_combo.addItem('_')
        self.mtmd_combo.activated[str].connect(self.set_mtmd)
        
        self.e_capsize_label = QtGui.QLabel("Error bar cap size")
        self.e_capsize_edit = QtGui.QLineEdit("{0:.2f}".format(self.e_capsize))
        self.e_capsize_edit.editingFinished.connect(self.set_e_capsize)
        
        self.e_capthick_label = QtGui.QLabel("Error bar cap thickness")
        self.e_capthick_edit = QtGui.QLineEdit("{0:.2f}".format(self.e_capthick))
        self.e_capthick_edit.editingFinished.connect(self.set_e_capthick)
        
        self.cted_button = QtGui.QPushButton("Set Z_xi Color")
        self.cted_button.pressed.connect(self.set_cted)
        
        self.ctmd_button = QtGui.QPushButton("Set Z_yi Color")
        self.ctmd_button.pressed.connect(self.set_ctmd)
        
        self.ctx_button = QtGui.QPushButton("Set T_x Color")
        self.ctx_button.pressed.connect(self.set_ctx)
        
        self.cty_button = QtGui.QPushButton("Set T_y Color")
        self.cty_button.pressed.connect(self.set_cty)
        
        self.cteo_button = QtGui.QPushButton("Set Original Data_xi Color")
        self.cteo_button.pressed.connect(self.set_cteo)
        
        self.ctmo_button = QtGui.QPushButton("Set Original Data_yi Color")
        self.ctmo_button.pressed.connect(self.set_ctmo)
        
        self.resod_limits_label = QtGui.QLabel("Off Diagonal Res. Limits (min, max)")
        
        self.resod_limits_min_edit = QtGui.QLineEdit()
        self.resod_limits_min_edit.editingFinished.connect(self.set_resod_min)        
        
        self.resod_limits_max_edit = QtGui.QLineEdit()
        self.resod_limits_max_edit.editingFinished.connect(self.set_resod_max)        
        
        self.resd_limits_label = QtGui.QLabel("Diagonal Res. Limits (min, max)")
        
        self.resd_limits_min_edit = QtGui.QLineEdit()
        self.resd_limits_min_edit.editingFinished.connect(self.set_resd_min)        
        
        self.resd_limits_max_edit = QtGui.QLineEdit()
        self.resd_limits_max_edit.editingFinished.connect(self.set_resd_max)  
        
        self.phaseod_limits_label = QtGui.QLabel("Off Diagonal phase. Limits (min, max)")
        
        self.phaseod_limits_min_edit = QtGui.QLineEdit()
        self.phaseod_limits_min_edit.editingFinished.connect(self.set_phaseod_min)        
        
        self.phaseod_limits_max_edit = QtGui.QLineEdit()
        self.phaseod_limits_max_edit.editingFinished.connect(self.set_phaseod_max)        
        
        self.phased_limits_label = QtGui.QLabel("Diagonal phase. Limits (min, max)")
        
        self.phased_limits_min_edit = QtGui.QLineEdit()
        self.phased_limits_min_edit.editingFinished.connect(self.set_phased_min)        
        
        self.phased_limits_max_edit = QtGui.QLineEdit()
        self.phased_limits_max_edit.editingFinished.connect(self.set_phased_max)        
        
        self.tip_x_limits_label = QtGui.QLabel("T_x limits (min, max)")
        
        self.tip_x_limits_min_edit = QtGui.QLineEdit()
        self.tip_x_limits_min_edit.editingFinished.connect(self.set_tip_x_min)        
        
        self.tip_x_limits_max_edit = QtGui.QLineEdit()
        self.tip_x_limits_max_edit.editingFinished.connect(self.set_tip_x_max)        
        
        self.tip_y_limits_label = QtGui.QLabel("T_y limits (min, max)")
        
        self.tip_y_limits_min_edit = QtGui.QLineEdit()
        self.tip_y_limits_min_edit.editingFinished.connect(self.set_tip_y_min)        
        
        self.tip_y_limits_max_edit = QtGui.QLineEdit()
        self.tip_y_limits_max_edit.editingFinished.connect(self.set_tip_y_max)        
        
        self.update_button = QtGui.QPushButton("Update Settings")
        self.update_button.pressed.connect(self.update_settings)

        ## --> layout        
        grid = QtGui.QGridLayout()
        
        grid.addWidget(self.fs_label, 0, 0)
        grid.addWidget(self.fs_edit, 0, 1)
        grid.addWidget(self.lw_label, 0, 2)
        grid.addWidget(self.lw_edit, 0, 3)
        grid.addWidget(self.ms_label, 1, 0)
        grid.addWidget(self.ms_edit, 1, 1)
        grid.addWidget(self.mted_label, 1, 2)
        grid.addWidget(self.mted_combo, 1, 3)
        grid.addWidget(self.mtmd_label, 1, 4)
        grid.addWidget(self.mtmd_combo, 1, 5)
        grid.addWidget(self.cted_button, 2, 0, 1, 3)
        grid.addWidget(self.ctmd_button, 2, 3, 1, 3)
        grid.addWidget(self.cteo_button, 3, 0, 1, 3)
        grid.addWidget(self.ctmo_button, 3, 3, 1, 3)
        grid.addWidget(self.ctx_button, 4, 0, 1, 3)
        grid.addWidget(self.cty_button, 4, 3, 1, 3)
        grid.addWidget(self.resod_limits_label, 5, 0)
        grid.addWidget(self.resod_limits_min_edit, 5, 1)
        grid.addWidget(self.resod_limits_max_edit, 5, 2)
        grid.addWidget(self.resd_limits_label, 5, 3)
        grid.addWidget(self.resd_limits_min_edit, 5, 4)
        grid.addWidget(self.resd_limits_max_edit, 5, 5)
        grid.addWidget(self.phaseod_limits_label, 6, 0)
        grid.addWidget(self.phaseod_limits_min_edit, 6, 1)
        grid.addWidget(self.phaseod_limits_max_edit, 6, 2)
        grid.addWidget(self.phased_limits_label, 6, 3)
        grid.addWidget(self.phased_limits_min_edit, 6, 4)
        grid.addWidget(self.phased_limits_max_edit, 6, 5)
        grid.addWidget(self.tip_x_limits_label, 7, 0)
        grid.addWidget(self.tip_x_limits_min_edit, 7, 1)
        grid.addWidget(self.tip_x_limits_max_edit, 7, 2)
        grid.addWidget(self.tip_y_limits_label, 7, 3)
        grid.addWidget(self.tip_y_limits_min_edit, 7, 4)
        grid.addWidget(self.tip_y_limits_max_edit, 7, 5)
        grid.addWidget(self.update_button, 10, 0, 1, 6)
        
        self.setLayout(grid)
        self.setWindowTitle("Plot Settings")
        self.show()
        
        
    def convert_color_to_qt(self, color):
        """
        convert decimal tuple to QColor object
        """
        r = int(color[0]*255)
        g = int(color[1]*255)
        b = int(color[2]*255)
        
        return QtGui.QColor(r, g, b)
        
    def set_fs(self):
        self.fs = float(str(self.fs_edit.text()))
        self.fs_edit.setText("{0:.2f}".format(self.fs))
        
    def set_lw(self):
        self.lw = float(str(self.lw_edit.text()))
        self.lw_edit.setText("{0:.2f}".format(self.lw))
        
    def set_ms(self):
        self.ms = float(str(self.ms_edit.text()))
        self.ms_edit.setText("{0:.2f}".format(self.ms))
        
    def set_e_capsize(self):
        self.e_capsize = float(str(self.e_capsize_edit.text()))
        self.e_capsize_edit.setText("{0:.2f}".format(self.e_capsize))
        
    def set_e_capthick(self):
        self.e_capthick = float(str(self.e_capthick_edit.text()))
        self.e_capthick_edit.setText("{0:.2f}".format(self.e_capthick))
        
    def set_mted(self, text):
        self.mted = text
        
    def set_mtmd(self, text):
        self.mtmd = text
        
    def set_resod_min(self):
        try:
            self._res_limits_od_min = float(str(self.resod_limits_min_edit.text()))
        except ValueError:
            self._res_limits_od_min = None           
    def set_resod_max(self):
        try:
            self._res_limits_od_max = float(str(self.resod_limits_max_edit.text()))
        except ValueError:
            self._res_limits_od_max = None
           
    def set_resd_min(self):
        try:
            self._res_limits_d_min = float(str(self.resd_limits_min_edit.text()))
        except ValueError:
            self._res_limits_d_min = None            
    def set_resd_max(self):
        try:
            self._res_limits_d_max = float(str(self.resd_limits_max_edit.text()))
        except ValueError:
            self._res_limits_d_max = None   
            
    def set_phaseod_min(self):
        try:
            self._phase_limits_od_min = float(str(self.phaseod_limits_min_edit.text()))
        except ValueError:
            self._phase_limits_od_min = None           
    def set_phaseod_max(self):
        try:
            self._phase_limits_od_max = float(str(self.phaseod_limits_max_edit.text()))
        except ValueError:
            self._phase_limits_od_max = None
           
    def set_phased_min(self):
        try:
            self._phase_limits_d_min = float(str(self.phased_limits_min_edit.text()))
        except ValueError:
            self._phase_limits_d_min = None            
    def set_phased_max(self):
        try:
            self._phase_limits_d_max = float(str(self.phased_limits_max_edit.text()))
        except ValueError:
            self._phase_limits_d_max = None
            
    def set_tip_x_min(self):
        try:
            self._tip_x_limits_min = float(str(self.tip_x_limits_min_edit.text()))
        except ValueError:
            self._tip_x_limits_min = None           
    def set_tip_x_max(self):
        try:
            self._tip_x_limits_max = float(str(self.tip_x_limits_max_edit.text()))
        except ValueError:
            self._tip_x_limits_max = None
           
    def set_tip_y_min(self):
        try:
            self._tip_y_limits_min = float(str(self.tip_y_limits_min_edit.text()))
        except ValueError:
            self._tip_y_limits_min = None            
    def set_tip_y_max(self):
        try:
            self._tip_y_limits_max = float(str(self.tip_y_limits_max_edit.text()))
        except ValueError:
            self._tip_y_limits_max = None           
        
        
    def set_cted(self):
        initial_color = self.convert_color_to_qt(self.cted)
        new_color = QtGui.QColorDialog.getColor(initial_color)
        
        r,g,b,a = new_color.getRgbF()
        
        self.cted = (r, g, b)
        
    def set_ctmd(self):
        initial_color = self.convert_color_to_qt(self.ctmd)
        new_color = QtGui.QColorDialog.getColor(initial_color)
        
        r,g,b,a = new_color.getRgbF()
        
        self.ctmd = (r, g, b)
        
    def set_ctx(self):
        initial_color = self.convert_color_to_qt(self.tipper_x_color)
        new_color = QtGui.QColorDialog.getColor(initial_color)
        
        r,g,b,a = new_color.getRgbF()
        
        self.tipper_x_color = (r, g, b)
        
    def set_cty(self):
        initial_color = self.convert_color_to_qt(self.tipper_y_color)
        new_color = QtGui.QColorDialog.getColor(initial_color)
        
        r,g,b,a = new_color.getRgbF()
        
        self.tipper_y_color = (r, g, b)
        
    def set_cteo(self):
        initial_color = self.convert_color_to_qt(self.cteo)
        new_color = QtGui.QColorDialog.getColor(initial_color)
        
        r,g,b,a = new_color.getRgbF()
        
        self.cteo = (r, g, b)
        
    def set_ctmo(self):
        initial_color = self.convert_color_to_qt(self.ctmo)
        new_color = QtGui.QColorDialog.getColor(initial_color)
        
        r,g,b,a = new_color.getRgbF()
        
        self.ctmo = (r, g, b)
      
    def update_settings(self):
        if self._res_limits_od_min != None and self._res_limits_od_max != None:
            self.res_limits_od = (self._res_limits_od_min,
                                  self._res_limits_od_max)
        else:
            self.res_limits_od = None
            
        if self._res_limits_d_min != None and self._res_limits_d_max != None:
            self.res_limits_d = (self._res_limits_d_min,
                                 self._res_limits_d_max)
        else:
            self.res_limits_d = None
            
        if self._phase_limits_od_min != None and self._phase_limits_od_max != None:
            self.phase_limits_od = (self._phase_limits_od_min,
                                  self._phase_limits_od_max)
        else:
            self.phase_limits_od = None
            
        if self._phase_limits_d_min != None and self._phase_limits_d_max != None:
            self.phase_limits_d = (self._phase_limits_d_min,
                                 self._phase_limits_d_max)
        else:
            self.phase_limits_d = None
            
        if self._tip_x_limits_min != None and self._tip_x_limits_max != None:
            self.tipper_x_limits = (self._tip_x_limits_min,
                                    self._tip_x_limits_max)
        else:
            self.tipper_x_limits = None
            
        if self._tip_y_limits_min != None and self._tip_y_limits_max != None:
            self.tipper_y_limits = (self._tip_y_limits_min,
                                    self._tip_y_limits_max)
        else:
            self.tipper_y_limits = None
            
        self.settings_updated.emit()
        
#==============================================================================
# edi text editor
#==============================================================================
class EDITextEditor(QtGui.QWidget):
    """
    class to edit the text of an .edi file
    """
    metadata_updated = QtCore.pyqtSignal()
    
    def __init__(self, edi_object):
        super(EDITextEditor, self).__init__()
        
        self.edi_obj = edi_object
        
        self.setup_ui()
        
    def setup_ui(self):
        
        self.setWindowTitle("EDI Text Editor")
        
        # header label font
        header_font = QtGui.QFont()
        header_font.setBold = True
        header_font.setPointSize (16)
        
        ##--> header information
        self.header_label = QtGui.QLabel("Header Information")
        self.header_label.setFont(header_font)
        
        self.header_acqby_label = QtGui.QLabel("Acquired By")
        self.header_acqby_edit = QtGui.QLineEdit(self.edi_obj.Header.acqby)
        self.header_acqby_edit.editingFinished.connect(self.header_set_acqby)
        
        self.header_acqdate_label = QtGui.QLabel("Acquired Date (YYYY-MM-DD)")
        self.header_acqdate_edit = QtGui.QLineEdit(self.edi_obj.Header.acqdate)
        self.header_acqdate_edit.editingFinished.connect(self.header_set_acqdate)
        
        self.header_dataid_label = QtGui.QLabel("Station Name")
        self.header_dataid_edit = QtGui.QLineEdit(self.edi_obj.Header.dataid)
        self.header_dataid_edit.editingFinished.connect(self.header_set_dataid)
        
        self.header_elev_label = QtGui.QLabel("Elevation (m)")
        self.header_elev_edit = QtGui.QLineEdit()
        if self.edi_obj.elev is None:
            self.header_elev_edit.setText('0.0')
        else:
            self.header_elev_edit.setText('{0:.1f}'.format(self.edi_obj.elev))
        
        self.header_elev_edit.editingFinished.connect(self.header_set_elev)
        
        self.header_empty_label = QtGui.QLabel("Empty Value")
        self.header_empty_edit = QtGui.QLineEdit('{0}'.format(self.edi_obj.Header.empty))
        self.header_empty_edit.editingFinished.connect(self.header_set_empty)
  
        self.header_fileby_label = QtGui.QLabel("File By")
        self.header_fileby_edit = QtGui.QLineEdit(self.edi_obj.Header.fileby)
        self.header_fileby_edit.editingFinished.connect(self.header_set_fileby)
  
        self.header_filedate_label = QtGui.QLabel("File Date (YYY-MM-DD)")
        self.header_filedate_edit = QtGui.QLineEdit(self.edi_obj.Header.filedate)
        self.header_filedate_edit.editingFinished.connect(self.header_set_filedate)
        
        self.header_lat_label = QtGui.QLabel("Latitude (decimal degrees)")
        self.header_lat_edit = QtGui.QLineEdit()
        if self.edi_obj.lat is None:
            self.header_lat_edit.setText('0.000000')
        else:
            self.header_lat_edit.setText('{0:.5f}'.format(self.edi_obj.lat))
        self.header_lat_edit.editingFinished.connect(self.header_set_lat)
        
        self.header_lon_label = QtGui.QLabel("Longitude (decimal degrees)")
        self.header_lon_edit = QtGui.QLineEdit()
        if self.edi_obj.lon is None:
            self.header_lon_edit.setText('0.000000')
        else:
            self.header_lon_edit.setText('{0:.5f}'.format(self.edi_obj.lon))
        self.header_lon_edit.editingFinished.connect(self.header_set_lon)

        self.header_loc_label = QtGui.QLabel("Location")
        self.header_loc_edit = QtGui.QLineEdit(self.edi_obj.Header.loc)
        self.header_loc_edit.editingFinished.connect(self.header_set_loc)

        self.header_progdate_label = QtGui.QLabel("Program Date")
        self.header_progdate_edit = QtGui.QLineEdit(self.edi_obj.Header.progdate)
        self.header_progdate_edit.editingFinished.connect(self.header_set_progdate)
        

        self.header_progvers_label = QtGui.QLabel("Program Version")
        self.header_progvers_edit = QtGui.QLineEdit(self.edi_obj.Header.progvers)
        self.header_progvers_edit.editingFinished.connect(self.header_set_progvers)
        
        ##--> Info
        self.info_label = QtGui.QLabel("Information Section")
        self.info_label.setFont(header_font)
        
        self.info_edit = QtGui.QTextEdit()
        self.info_edit.setMinimumWidth(500)
        try:
            info_str = ''.join(self.edi_obj.Info.write_info())
        except TypeError:
            info_str = ''
        self.info_edit.setText(info_str)
        self.info_edit.textChanged.connect(self.info_set_text)
        
        ##--> define measurement
        self.define_label = QtGui.QLabel('Define Measurement')
        self.define_label.setFont(header_font)

        self.define_maxchan_label = QtGui.QLabel('Maximum Channels')
        self.define_maxchan_edit = QtGui.QLineEdit('{0}'.format(self.edi_obj.Define_measurement.maxchan))        
        self.define_maxchan_edit.editingFinished.connect(self.define_set_maxchan)
        
        self.define_maxrun_label = QtGui.QLabel('Maximum Runs')
        self.define_maxrun_edit = QtGui.QLineEdit('{0}'.format(self.edi_obj.Define_measurement.maxrun))        
        self.define_maxrun_edit.editingFinished.connect(self.define_set_maxrun)
        
        self.define_maxmeas_label = QtGui.QLabel('Maximum Measurements')
        self.define_maxmeas_edit = QtGui.QLineEdit('{0}'.format(self.edi_obj.Define_measurement.maxmeas))        
        self.define_maxmeas_edit.editingFinished.connect(self.define_set_maxmeas)
        
        self.define_refelev_label = QtGui.QLabel('Reference Elevation (m)')
        self.define_refelev_edit = QtGui.QLineEdit()
        if self.edi_obj.Define_measurement.refelev is None:
            self.define_refelev_edit.setText('0.0')
        else:
            self.define_refelev_edit.setText('{0:.5f}'.format(self.edi_obj.Define_measurement.refelev))        
        self.define_refelev_edit.editingFinished.connect(self.define_set_refelev)
        
        self.define_reflat_label = QtGui.QLabel('Reference Latitude (dec. deg)')
        self.define_reflat_edit = QtGui.QLineEdit()
        if self.edi_obj.Define_measurement.refelev is None:
            self.define_reflat_edit.setText('0.0000000')
        else:
            self.define_reflat_edit.setText('{0:.5f}'.format(self.edi_obj.Define_measurement.reflat))         
        self.define_reflat_edit.editingFinished.connect(self.define_set_reflat)
        
        self.define_reflon_label = QtGui.QLabel('Reference Longitude (dec. deg)')
        self.define_reflon_edit = QtGui.QLineEdit()
        if self.edi_obj.Define_measurement.reflon is None:
            self.define_reflon_edit.setText('0.000000')
        else:
            self.define_reflon_edit.setText('{0:.5f}'.format(self.edi_obj.Define_measurement.reflon)) 
        self.define_reflon_edit.editingFinished.connect(self.define_set_reflon)
        
        #self.define_refloc_label = QtGui.QLabel('Reference Location')
        #self.define_refloc_edit = QtGui.QLineEdit('{0}'.format(self.edi_obj.Define_measurement.refloc))        
        #self.define_refloc_edit.editingFinished.connect(self.define_set_refloc)
        
        self.define_reftype_label = QtGui.QLabel('Reference Type')
        self.define_reftype_edit = QtGui.QLineEdit('{0}'.format(self.edi_obj.Define_measurement.reftype))        
        self.define_reftype_edit.editingFinished.connect(self.define_set_reftype)

        self.define_units_label = QtGui.QLabel('Distance Units')
        self.define_units_edit = QtGui.QLineEdit('{0}'.format(self.edi_obj.Define_measurement.units))        
        self.define_units_edit.editingFinished.connect(self.define_set_units)

        self.meas_help = QtGui.QLabel()
        self.meas_help.setText('Assume x is northing (m), y is easting (m), North = 0 deg, East = 90 deg')
        h_ch_list = ['HX', 'HY', 'HZ', 'RHX', 'RHY']        
        self.meas_h01_label = QtGui.QLabel("HMEAS")
        self.meas_h01_id_label = QtGui.QLabel("ID")
        self.meas_h01_id_edit = QtGui.QLineEdit()
        self.meas_h01_ct_label = QtGui.QLabel("CHTYPE")
        self.meas_h01_ct_combo = QtGui.QComboBox()
        for ch in h_ch_list:
            self.meas_h01_ct_combo.addItem(ch)
        self.meas_h01_x_label = QtGui.QLabel("X (m)")
        self.meas_h01_x_edit = QtGui.QLineEdit()
        self.meas_h01_y_label = QtGui.QLabel("Y (m)")
        self.meas_h01_y_edit = QtGui.QLineEdit()
        self.meas_h01_azm_label = QtGui.QLabel("Azimtuh (deg)")
        self.meas_h01_azm_edit = QtGui.QLineEdit()
        self.meas_h01_acqchn_label = QtGui.QLabel("Acq. Channel")
        self.meas_h01_acqchn_combo = QtGui.QComboBox()
        for ch in h_ch_list:
            self.meas_h01_acqchn_combo.addItem(ch)
        
        self.meas_h02_label = QtGui.QLabel("HMEAS")
        self.meas_h02_id_label = QtGui.QLabel("ID")
        self.meas_h02_id_edit = QtGui.QLineEdit()
        self.meas_h02_ct_label = QtGui.QLabel("CHTYPE")
        self.meas_h02_ct_combo = QtGui.QComboBox()
        for ch in h_ch_list:
            self.meas_h02_ct_combo.addItem(ch)
        self.meas_h02_x_label = QtGui.QLabel("X (m)")
        self.meas_h02_x_edit = QtGui.QLineEdit()
        self.meas_h02_y_label = QtGui.QLabel("Y (m)")
        self.meas_h02_y_edit = QtGui.QLineEdit()
        self.meas_h02_azm_label = QtGui.QLabel("Azimtuh (deg)")
        self.meas_h02_azm_edit = QtGui.QLineEdit()
        self.meas_h02_acqchn_label = QtGui.QLabel("Acq. Channel")
        self.meas_h02_acqchn_combo = QtGui.QComboBox()
        for ch in h_ch_list:
            self.meas_h02_acqchn_combo.addItem(ch)
        
        self.meas_h03_label = QtGui.QLabel("HMEAS")
        self.meas_h03_id_label = QtGui.QLabel("ID")
        self.meas_h03_id_edit = QtGui.QLineEdit()
        self.meas_h03_ct_label = QtGui.QLabel("CHTYPE")
        self.meas_h03_ct_combo = QtGui.QComboBox()
        for ch in h_ch_list:
            self.meas_h03_ct_combo.addItem(ch)
        self.meas_h03_x_label = QtGui.QLabel("X (m)")
        self.meas_h03_x_edit = QtGui.QLineEdit()
        self.meas_h03_y_label = QtGui.QLabel("Y (m)")
        self.meas_h03_y_edit = QtGui.QLineEdit()
        self.meas_h03_azm_label = QtGui.QLabel("Azimtuh (deg)")
        self.meas_h03_azm_edit = QtGui.QLineEdit()
        self.meas_h03_acqchn_label = QtGui.QLabel("Acq. Channel")
        self.meas_h03_acqchn_combo = QtGui.QComboBox()
        for ch in h_ch_list:
            self.meas_h03_acqchn_combo.addItem(ch)
        
        self.meas_hr1_label = QtGui.QLabel("HMEAS")
        self.meas_hr1_id_label = QtGui.QLabel("ID")
        self.meas_hr1_id_edit = QtGui.QLineEdit()
        self.meas_hr1_ct_label = QtGui.QLabel("CHTYPE")
        self.meas_hr1_ct_combo = QtGui.QComboBox()
        for ch in h_ch_list:
            self.meas_hr1_ct_combo.addItem(ch)
        self.meas_hr1_x_label = QtGui.QLabel("X (m)")
        self.meas_hr1_x_edit = QtGui.QLineEdit()
        self.meas_hr1_y_label = QtGui.QLabel("Y (m)")
        self.meas_hr1_y_edit = QtGui.QLineEdit()
        self.meas_hr1_azm_label = QtGui.QLabel("Azimtuh (deg)")
        self.meas_hr1_azm_edit = QtGui.QLineEdit()
        self.meas_hr1_acqchn_label = QtGui.QLabel("Acq. Channel")
        self.meas_hr1_acqchn_combo = QtGui.QComboBox()
        for ch in h_ch_list:
            self.meas_hr1_acqchn_combo.addItem(ch)
        
        self.meas_hr2_label = QtGui.QLabel("HMEAS")
        self.meas_hr2_id_label = QtGui.QLabel("ID")
        self.meas_hr2_id_edit = QtGui.QLineEdit()
        self.meas_hr2_ct_label = QtGui.QLabel("CHTYPE")
        self.meas_hr2_ct_combo = QtGui.QComboBox()
        for ch in h_ch_list:
            self.meas_hr2_ct_combo.addItem(ch)
        self.meas_hr2_x_label = QtGui.QLabel("X (m)")
        self.meas_hr2_x_edit = QtGui.QLineEdit()
        self.meas_hr2_y_label = QtGui.QLabel("Y (m)")
        self.meas_hr2_y_edit = QtGui.QLineEdit()
        self.meas_hr2_azm_label = QtGui.QLabel("Azimtuh (deg)")
        self.meas_hr2_azm_edit = QtGui.QLineEdit()
        self.meas_hr2_acqchn_label = QtGui.QLabel("Acq. Channel")
        self.meas_hr2_acqchn_combo = QtGui.QComboBox()
        for ch in h_ch_list:
            self.meas_hr2_acqchn_combo.addItem(ch)
        
        e_ch_list = ['EX', 'EY', 'EZ']
        self.meas_e01_label = QtGui.QLabel("EMEAS")
        self.meas_e01_id_label = QtGui.QLabel("ID")
        self.meas_e01_id_edit = QtGui.QLineEdit()
        self.meas_e01_ct_label = QtGui.QLabel("CHTYPE")
        self.meas_e01_ct_combo = QtGui.QComboBox()
        for ch in e_ch_list:
            self.meas_e01_ct_combo.addItem(ch)
        self.meas_e01_x_label = QtGui.QLabel("X (m)")
        self.meas_e01_x_edit = QtGui.QLineEdit()
        self.meas_e01_y_label = QtGui.QLabel("Y (m)")
        self.meas_e01_y_edit = QtGui.QLineEdit()
        self.meas_e01_x2_label = QtGui.QLabel("X2 (m)")
        self.meas_e01_x2_edit = QtGui.QLineEdit()
        self.meas_e01_y2_label = QtGui.QLabel("Y2 (m)")
        self.meas_e01_y2_edit = QtGui.QLineEdit()
        self.meas_e01_acqchn_label = QtGui.QLabel("Acq. Channel")
        self.meas_e01_acqchn_combo = QtGui.QComboBox()
        for ch in e_ch_list:
            self.meas_e01_acqchn_combo.addItem(ch)
        
        self.meas_e02_label = QtGui.QLabel("EMEAS")
        self.meas_e02_id_label = QtGui.QLabel("ID")
        self.meas_e02_id_edit = QtGui.QLineEdit()
        self.meas_e02_ct_label = QtGui.QLabel("CHTYPE")
        self.meas_e02_ct_combo = QtGui.QComboBox()
        for ch in e_ch_list:
            self.meas_e02_ct_combo.addItem(ch)
        self.meas_e02_x_label = QtGui.QLabel("X (m)")
        self.meas_e02_x_edit = QtGui.QLineEdit()
        self.meas_e02_y_label = QtGui.QLabel("Y (m)")
        self.meas_e02_y_edit = QtGui.QLineEdit()
        self.meas_e02_x2_label = QtGui.QLabel("X2 (m)")
        self.meas_e02_x2_edit = QtGui.QLineEdit()
        self.meas_e02_y2_label = QtGui.QLabel("Y2 (m)")
        self.meas_e02_y2_edit = QtGui.QLineEdit()
        self.meas_e02_acqchn_label = QtGui.QLabel("Acq. Channel")
        self.meas_e02_acqchn_combo = QtGui.QComboBox()
        for ch in e_ch_list:
            self.meas_e02_acqchn_combo.addItem(ch)
    
        ##--> Update button
        self.update_button = QtGui.QPushButton('Update')
        self.update_button.pressed.connect(self.update_metadata)
        
        ## --> Layout    
        header_layout = QtGui.QGridLayout()
        header_layout.addWidget(self.header_label, 0, 0)
        header_layout.addWidget(self.header_acqby_label, 1, 0)
        header_layout.addWidget(self.header_acqby_edit, 1, 1)
        header_layout.addWidget(self.header_acqdate_label, 2, 0)
        header_layout.addWidget(self.header_acqdate_edit, 2, 1)
        header_layout.addWidget(self.header_dataid_label, 3, 0)
        header_layout.addWidget(self.header_dataid_edit, 3, 1)
        header_layout.addWidget(self.header_elev_label, 4, 0)
        header_layout.addWidget(self.header_elev_edit, 4, 1)
        header_layout.addWidget(self.header_empty_label, 5, 0)
        header_layout.addWidget(self.header_empty_edit, 5, 1)
        header_layout.addWidget(self.header_fileby_label, 6, 0)
        header_layout.addWidget(self.header_fileby_edit, 6, 1)
        header_layout.addWidget(self.header_filedate_label, 7, 0)
        header_layout.addWidget(self.header_filedate_edit, 7, 1)
        header_layout.addWidget(self.header_lat_label, 8, 0)
        header_layout.addWidget(self.header_lat_edit, 8, 1)
        header_layout.addWidget(self.header_lon_label, 9, 0)
        header_layout.addWidget(self.header_lon_edit, 9, 1)
        header_layout.addWidget(self.header_loc_label, 10, 0)
        header_layout.addWidget(self.header_loc_edit, 10, 1)
        header_layout.addWidget(self.header_progdate_label, 11, 0)
        header_layout.addWidget(self.header_progdate_edit, 11, 1)
        header_layout.addWidget(self.header_progvers_label, 12, 0)
        header_layout.addWidget(self.header_progvers_edit, 12, 1)
        
        info_layout = QtGui.QVBoxLayout()
        info_layout.addWidget(self.info_label)
        info_layout.addWidget(self.info_edit)
        
        define_layout = QtGui.QGridLayout()
        define_layout.addWidget(self.define_label, 0, 0)
        define_layout.addWidget(self.define_maxchan_label, 1, 0)
        define_layout.addWidget(self.define_maxchan_edit, 1, 1)
        define_layout.addWidget(self.define_maxmeas_label, 2, 0)
        define_layout.addWidget(self.define_maxmeas_edit, 2, 1)
        define_layout.addWidget(self.define_maxrun_label, 3, 0)
        define_layout.addWidget(self.define_maxrun_edit, 3, 1)
        define_layout.addWidget(self.define_refelev_label, 4, 0)
        define_layout.addWidget(self.define_refelev_edit, 4, 1)
        define_layout.addWidget(self.define_reflat_label, 5, 0)
        define_layout.addWidget(self.define_reflat_edit, 5, 1)
        define_layout.addWidget(self.define_reflon_label, 6, 0)
        define_layout.addWidget(self.define_reflon_edit, 6, 1)
        define_layout.addWidget(self.define_reftype_label, 7, 0)
        define_layout.addWidget(self.define_reftype_edit, 7, 1)
        define_layout.addWidget(self.define_units_label, 8, 0)
        define_layout.addWidget(self.define_units_edit, 8, 1)
        #define_layout.addWidget(self.define_refloc_label, 7, 0)
        #define_layout.addWidget(self.define_refloc_edit, 7, 1)
        
        meas_layout = QtGui.QGridLayout()
        meas_layout.addWidget(self.meas_help, 0, 0, 1, 10)
        meas_layout.addWidget(self.meas_h01_label, 1, 0)
        meas_layout.addWidget(self.meas_h01_id_label, 1, 1)
        meas_layout.addWidget(self.meas_h01_id_edit, 1, 2)
        meas_layout.addWidget(self.meas_h01_ct_label, 1, 3)
        meas_layout.addWidget(self.meas_h01_ct_combo, 1, 4)
        meas_layout.addWidget(self.meas_h01_x_label, 1, 5)
        meas_layout.addWidget(self.meas_h01_x_edit, 1, 6)
        meas_layout.addWidget(self.meas_h01_y_label, 1, 7)
        meas_layout.addWidget(self.meas_h01_y_edit, 1, 8)
        meas_layout.addWidget(self.meas_h01_azm_label, 1, 9)
        meas_layout.addWidget(self.meas_h01_azm_edit, 1, 10)
        meas_layout.addWidget(self.meas_h01_acqchn_label, 1, 13)
        meas_layout.addWidget(self.meas_h01_acqchn_combo, 1, 14)
        
        meas_layout.addWidget(self.meas_h02_label, 2, 0)
        meas_layout.addWidget(self.meas_h02_id_label, 2, 1)
        meas_layout.addWidget(self.meas_h02_id_edit, 2, 2)
        meas_layout.addWidget(self.meas_h02_ct_label, 2, 3)
        meas_layout.addWidget(self.meas_h02_ct_combo, 2, 4)
        meas_layout.addWidget(self.meas_h02_x_label, 2, 5)
        meas_layout.addWidget(self.meas_h02_x_edit, 2, 6)
        meas_layout.addWidget(self.meas_h02_y_label, 2, 7)
        meas_layout.addWidget(self.meas_h02_y_edit, 2, 8)
        meas_layout.addWidget(self.meas_h02_azm_label, 2, 9)
        meas_layout.addWidget(self.meas_h02_azm_edit, 2, 10)
        meas_layout.addWidget(self.meas_h02_acqchn_label, 2, 13)
        meas_layout.addWidget(self.meas_h02_acqchn_combo, 2, 14)
        
        meas_layout.addWidget(self.meas_h03_label, 3, 0)
        meas_layout.addWidget(self.meas_h03_id_label, 3, 1)
        meas_layout.addWidget(self.meas_h03_id_edit, 3, 2)
        meas_layout.addWidget(self.meas_h03_ct_label, 3, 3)
        meas_layout.addWidget(self.meas_h03_ct_combo, 3, 4)
        meas_layout.addWidget(self.meas_h03_x_label, 3, 5)
        meas_layout.addWidget(self.meas_h03_x_edit, 3, 6)
        meas_layout.addWidget(self.meas_h03_y_label, 3, 7)
        meas_layout.addWidget(self.meas_h03_y_edit, 3, 8)
        meas_layout.addWidget(self.meas_h03_azm_label, 3, 9)
        meas_layout.addWidget(self.meas_h03_azm_edit, 3, 10)
        meas_layout.addWidget(self.meas_h03_acqchn_label, 3, 13)
        meas_layout.addWidget(self.meas_h03_acqchn_combo, 3, 14)
        
        meas_layout.addWidget(self.meas_hr1_label, 4, 0)
        meas_layout.addWidget(self.meas_hr1_id_label, 4, 1)
        meas_layout.addWidget(self.meas_hr1_id_edit, 4, 2)
        meas_layout.addWidget(self.meas_hr1_ct_label, 4, 3)
        meas_layout.addWidget(self.meas_hr1_ct_combo, 4, 4)
        meas_layout.addWidget(self.meas_hr1_x_label, 4, 5)
        meas_layout.addWidget(self.meas_hr1_x_edit, 4, 6)
        meas_layout.addWidget(self.meas_hr1_y_label, 4, 7)
        meas_layout.addWidget(self.meas_hr1_y_edit, 4, 8)
        meas_layout.addWidget(self.meas_hr1_azm_label, 4, 9)
        meas_layout.addWidget(self.meas_hr1_azm_edit, 4, 10)
        meas_layout.addWidget(self.meas_hr1_acqchn_label, 4, 13)
        meas_layout.addWidget(self.meas_hr1_acqchn_combo, 4, 14)
        
        meas_layout.addWidget(self.meas_hr2_label, 5, 0)
        meas_layout.addWidget(self.meas_hr2_id_label, 5, 1)
        meas_layout.addWidget(self.meas_hr2_id_edit, 5, 2)
        meas_layout.addWidget(self.meas_hr2_ct_label, 5, 3)
        meas_layout.addWidget(self.meas_hr2_ct_combo, 5, 4)
        meas_layout.addWidget(self.meas_hr2_x_label, 5, 5)
        meas_layout.addWidget(self.meas_hr2_x_edit, 5, 6)
        meas_layout.addWidget(self.meas_hr2_y_label, 5, 7)
        meas_layout.addWidget(self.meas_hr2_y_edit, 5, 8)
        meas_layout.addWidget(self.meas_hr2_azm_label, 5, 9)
        meas_layout.addWidget(self.meas_hr2_azm_edit, 5, 10)
        meas_layout.addWidget(self.meas_hr2_acqchn_label, 5, 13)
        meas_layout.addWidget(self.meas_hr2_acqchn_combo, 5, 14)
        
        meas_layout.addWidget(self.meas_e01_label, 6, 0)
        meas_layout.addWidget(self.meas_e01_id_label, 6, 1)
        meas_layout.addWidget(self.meas_e01_id_edit, 6, 2)
        meas_layout.addWidget(self.meas_e01_ct_label, 6, 3)
        meas_layout.addWidget(self.meas_e01_ct_combo, 6, 4)
        meas_layout.addWidget(self.meas_e01_x_label, 6, 5)
        meas_layout.addWidget(self.meas_e01_x_edit, 6, 6)
        meas_layout.addWidget(self.meas_e01_y_label, 6, 7)
        meas_layout.addWidget(self.meas_e01_y_edit, 6, 8)
        meas_layout.addWidget(self.meas_e01_x2_label, 6, 9)
        meas_layout.addWidget(self.meas_e01_x2_edit, 6, 10)
        meas_layout.addWidget(self.meas_e01_y2_label, 6, 11)
        meas_layout.addWidget(self.meas_e01_y2_edit, 6, 12)
        meas_layout.addWidget(self.meas_e01_acqchn_label, 6, 13)
        meas_layout.addWidget(self.meas_e01_acqchn_combo, 6, 14)
        
        meas_layout.addWidget(self.meas_e02_label, 7, 0)
        meas_layout.addWidget(self.meas_e02_id_label, 7, 1)
        meas_layout.addWidget(self.meas_e02_id_edit, 7, 2)
        meas_layout.addWidget(self.meas_e02_ct_label, 7, 3)
        meas_layout.addWidget(self.meas_e02_ct_combo, 7, 4)
        meas_layout.addWidget(self.meas_e02_x_label, 7, 5)
        meas_layout.addWidget(self.meas_e02_x_edit, 7, 6)
        meas_layout.addWidget(self.meas_e02_y_label, 7, 7)
        meas_layout.addWidget(self.meas_e02_y_edit, 7, 8)
        meas_layout.addWidget(self.meas_e02_x2_label, 7, 9)
        meas_layout.addWidget(self.meas_e02_x2_edit, 7, 10)
        meas_layout.addWidget(self.meas_e02_y2_label, 7, 11)
        meas_layout.addWidget(self.meas_e02_y2_edit, 7, 12)
        meas_layout.addWidget(self.meas_e02_acqchn_label, 7, 13)
        meas_layout.addWidget(self.meas_e02_acqchn_combo, 7, 14)
        
        v_layout = QtGui.QVBoxLayout()
        v_layout.addLayout(header_layout)        
        v_layout.addLayout(define_layout)        
        
        h_layout = QtGui.QHBoxLayout()
        h_layout.addLayout(v_layout)
        h_layout.addLayout(info_layout)
        
        final_layout = QtGui.QVBoxLayout()
        final_layout.addLayout(h_layout)
        final_layout.addLayout(meas_layout)
        final_layout.addWidget(self.update_button)
        
        self.setLayout(final_layout)
        
        self.show()
        
    def header_set_acqby(self):
        self.edi_obj.Header.acqby = str(self.header_acqby_edit.text())
        self.header_acqby_edit.setText(self.edi_obj.Header.acqby)
        
    def header_set_acqdate(self):
        self.edi_obj.Header.acqdate = str(self.header_acqdate_edit.text())
        self.header_acqdate_edit.setText(self.edi_obj.Header.acqdate)
        
    def header_set_dataid(self):
        self.edi_obj.Header.dataid = str(self.header_dataid_edit.text())
        self.header_dataid_edit.setText(self.edi_obj.Header.dataid)
        
    def header_set_elev(self):
        self.edi_obj.elev = float(str(self.header_elev_edit.text()))
        self.header_elev_edit.setText('{0:.1f}'.format(self.edi_obj.elev))
        
    def header_set_empty(self):
        self.edi_obj.Header.empty = float(str(self.header_elev_edit.text()))
        self.header_empty_edit.setText('{0:.2e}'.format(self.edi_obj.Header.empty))
        
    def header_set_fileby(self):
        self.edi_obj.Header.fileby = str(self.header_fileby_edit.text())
        self.header_fileby_edit.setText('{0}'.format(self.edi_obj.Header.fileby))
    
    def header_set_filedate(self):
        self.edi_obj.Header.filedate = str(self.header_filedate_edit.text())
        self.header_filedate_edit.setText('{0}'.format(self.edi_obj.Header.filedate))
        
    def header_set_lat(self):
        self.edi_obj.lat = str(self.header_lat_edit.text())
        self.header_lat_edit.setText('{0:.5f}'.format(self.edi_obj.lat))
        
    def header_set_lon(self):
        self.edi_obj.lon = str(self.header_lon_edit.text())
        self.header_lon_edit.setText('{0:.5f}'.format(self.edi_obj.lon))
    
    def header_set_loc(self):
        self.edi_obj.Header.loc = str(self.header_loc_edit.text())
        self.header_loc_edit.setText('{0}'.format(self.edi_obj.Header.loc))
    
    def header_set_progdate(self):
        self.edi_obj.Header.progdate = str(self.header_progdate_edit.text())
        self.header_progdate_edit.setText('{0}'.format(self.edi_obj.Header.progdate))
        
    def header_set_progvers(self):
        self.edi_obj.Header.progvers = str(self.header_progvers_edit.text())
        self.header_progvers_edit.setText('{0}'.format(self.edi_obj.Header.progvers))
        
    def info_set_text(self):
        new_info_str = self.info_edit.toPlainText()
        new_info_list = [str(nn) for nn in new_info_str.split('\n')]
        self.edi_obj.Info.info_lines = self.edi_obj.Info._validate_info_list(new_info_list)

    def define_set_maxchan(self):
        self.edi_obj.Define_measurement.maxchan = int(str(self.define_maxchan_edit.text()))
        self.define_maxchan_edit.setText('{0}'.format(self.edi_obj.Define_measurement.maxchan))
        
    def define_set_maxrun(self):
        self.edi_obj.Define_measurement.maxrun = int(str(self.define_maxrun_edit.text()))
        self.define_maxrun_edit.setText('{0}'.format(self.edi_obj.Define_measurement.maxrun))
        
    def define_set_maxmeas(self):
        self.edi_obj.Define_measurement.maxmeas = int(str(self.define_maxmeas_edit.text()))
        self.define_maxmeas_edit.setText('{0}'.format(self.edi_obj.Define_measurement.maxmeas))
        
    def define_set_refelev(self):
        value = mt.MTedi.MTft._assert_position_format('elev', 
                                                      str(self.define_refelev_edit.text()))
        self.edi_obj.Define_measurement.refelev = value
        self.define_refelev_edit.setText('{0:.2f}'.format(value))
        
    def define_set_reflat(self):
        value = mt.MTedi.MTft._assert_position_format('lat', 
                                                      str(self.define_reflat_edit.text()))
        self.edi_obj.Define_measurement.reflat = value
        self.define_reflat_edit.setText('{0:.5f}'.format(value))
        
    def define_set_reflon(self):
        value = mt.MTedi.MTft._assert_position_format('lon', 
                                                      str(self.define_reflon_edit.text()))
        self.edi_obj.Define_measurement.reflon = value
        self.define_reflon_edit.setText('{0:.5f}'.format(value))

#    def define_set_refloc(self):
#        self.edi_obj.Define_measurement.refloc = str(self.define_refloc_edit.text())
#        self.define_refloc_edit.setText('{0}'.format(self.edi_obj.Define_measurement.refloc))
#        
    def define_set_reftype(self):
        self.edi_obj.Define_measurement.reftype = str(self.define_reftype_edit.text())
        self.define_reftype_edit.setText('{0}'.format(self.edi_obj.Define_measurement.reftype))
        
    def define_set_units(self):
        self.edi_obj.Define_measurement.units = str(self.define_units_edit.text())
        self.define_units_edit.setText('{0}'.format(self.edi_obj.Define_measurement.units))
        
        

    def update_metadata(self):
        self.metadata_updated.emit()
        
#==============================================================================
# Def Main
#==============================================================================
def main():
    app = QtGui.QApplication(sys.argv)
    ui = EDI_Editor_Window()
    ui.ui_setup()
    ui.show()
    sys.exit(app.exec_())
    
if __name__ == '__main__':
    main()