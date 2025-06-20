"""
Camera streaming module for an IDS camera.
Contains wrapper class CameraStream, that wraps the IDS Peak API

Author:
    Theodor Kapler <theodor.kapler@student.kit.edu>
"""

import threading
import cv2
from ids_peak import ids_peak
from ids_peak import ids_peak_ipl_extension
from datetime import timedelta

class CameraStream:
    """
    A class to stream images from an IDS camera in the background.
    """

    def __init__(self, frame_rate=30, exposure_time=10000, resize=(500, 500)):
        """
        Initializes the CameraStream class and starts the camera stream in a separate thread.

        Args:
            frame_rate (int): Frame rate for the camera stream.
            exposure_time (double): Exposure time in microseconds.
            resize (tuple): Resize dimensions for the output image.
        """
        # Member variables to control the camera stream
        self.running = True
        self.frame_rate = frame_rate
        self.exposure_time = exposure_time
        self.resize = resize

        # Member variables to store the latest data
        self.timestamp = None
        self.frame = None
        self.timing_offset = None

        # Initialize camera streaming in a separate thread
        self.thread = threading.Thread(target=self.camera_loop)
        self.thread.daemon = True
        self.thread.start()

    def camera_loop(self):
        """
        Internal method to handle camera initialization and image streaming.
        Inspired by the example from the IDS peak library at https://pypi.org/project/ids-peak/
        """
        ids_peak.Library.Initialize()
        device_manager = ids_peak.DeviceManager.Instance()

        try:
            device_manager.Update()
            if device_manager.Devices().empty():
                print("No IDS camera found.")
                self.running = False
                return

            device = device_manager.Devices()[0].OpenDevice(ids_peak.DeviceAccessType_Control)
            remote_nodemap = device.RemoteDevice().NodeMaps()[0]

            # Set acquisition parameters
            remote_nodemap.FindNode("AcquisitionFrameRate").SetValue(self.frame_rate)
            remote_nodemap.FindNode("ExposureTime").SetValue(self.exposure_time)

            # Enable Metadata (Chunks) for timestamp retrieval
            remote_nodemap.FindNode("ChunkModeActive").SetValue(True)
            remote_nodemap.FindNode("ChunkSelector").SetCurrentEntry("Timestamp")
            remote_nodemap.FindNode("ChunkEnable").SetValue(True)

            # Prepare data stream
            data_stream = device.DataStreams()[0].OpenDataStream()
            payload_size = remote_nodemap.FindNode("PayloadSize").Value()
            for _ in range(data_stream.NumBuffersAnnouncedMinRequired()):
                buffer = data_stream.AllocAndAnnounceBuffer(payload_size)
                data_stream.QueueBuffer(buffer)

            remote_nodemap.FindNode("TLParamsLocked").SetValue(1)
            data_stream.StartAcquisition()
            remote_nodemap.FindNode("AcquisitionStart").Execute()
            remote_nodemap.FindNode("AcquisitionStart").WaitUntilDone()

            print("Camera stream started.")

            while self.running:
                try:
                    buffer = data_stream.WaitForFinishedBuffer(1000)

                    remote_nodemap.UpdateChunkNodes(buffer)

                    frame = ids_peak_ipl_extension.BufferToImage(buffer)
                    frame = frame.get_numpy_2D()
                    frame = cv2.cvtColor(frame, cv2.COLOR_BAYER_BG2BGR) # Convert Bayer pattern to BGR format
                    if self.resize:
                        self.frame = cv2.resize(frame, self.resize, interpolation=cv2.INTER_LINEAR)
                    else:
                        self.frame = frame

                    timestamp = remote_nodemap.FindNode("ChunkTimestamp").Value()
                    self.timestamp = timedelta(seconds=timestamp / 1e9)  # Convert nanoseconds to seconds

                    data_stream.QueueBuffer(buffer)
                except Exception as e:
                    print(f"Streaming exception: {e}")
                    break

            # Stop stream
            remote_nodemap.FindNode("AcquisitionStop").Execute()
            remote_nodemap.FindNode("AcquisitionStop").WaitUntilDone()
            data_stream.StopAcquisition(ids_peak.AcquisitionStopMode_Default)
            data_stream.Flush(ids_peak.DataStreamFlushMode_DiscardAll)
            for buffer in data_stream.AnnouncedBuffers():
                data_stream.RevokeBuffer(buffer)
            remote_nodemap.FindNode("TLParamsLocked").SetValue(0)

        except Exception as e:
            print(f"Camera setup failed: {e}")

        finally:
            ids_peak.Library.Close()
            print("Camera stream stopped.")

    def start_timing(self):
        """
        Sets the current timestamp as the zero reference for relative timing.
        """
        self.timing_offset = self.timestamp

    def get_current_data(self):
        """
        Returns the latest image frame captured by the camera.

        Returns:
            dict: A dictionary containing the timestamp and the latest image frame.
        """
        if self.timing_offset is not None:
            timestamp = self.timestamp - self.timing_offset
        else:
            timestamp = self.timestamp

        return {'timestamp': timestamp, 'frame': self.frame}

    def stop(self):
        """
        Stops the camera stream and releases resources.
        """
        self.running = False
        self.thread.join()

