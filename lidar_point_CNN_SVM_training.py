import struct
import rosbag
import pandas as pd
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
from tensorflow import keras
from keras import Sequential
from keras.layers import Conv1D, BatchNormalization, MaxPooling1D, Dropout, UpSampling1D, Dense, Flatten
from keras.optimizers import Adam
from keras.callbacks import ReduceLROnPlateau
from sklearn.svm import SVR
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error
from keras.preprocessing.sequence import pad_sequences
from joblib import dump
import os
import datetime
import logging
import sys
from keras.callbacks import Callback
from mpl_toolkits.mplot3d import Axes3D  # This is needed for '3d' projection


class TrainingLogger(Callback):
    def on_epoch_end(self, epoch, logs=None):
        if logs is not None:
            logger.info(f'Epoch {epoch + 1}: Loss: {logs["loss"]}, Val Loss: {logs["val_loss"]}')


# Current timestamp to create a unique folder
current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
current_folder = f"slfn_test__{current_time}"
os.makedirs(current_folder, exist_ok=True)  # Create the directory if it doesn't exist

# Setup logging
logger = logging.getLogger('LidarTestLogger')
logger.setLevel(logging.INFO)

# Log file
log_filename = os.path.join(current_folder, 'test_log.txt')
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

def calculate_mean_percentage_error(actual, predicted):
    # Avoid division by zero and handle cases where actual values are zero
    non_zero_mask = actual != 0
    percentage_errors = np.where(non_zero_mask, 100 * (actual - predicted) / actual, 0)
    mean_percentage_errors = np.mean(percentage_errors, axis=0)
    return mean_percentage_errors


def extract_data_from_bag(bag_file, seq_offset):
    bag = rosbag.Bag(bag_file)
    point_cloud_data = {}
    lidar_transform_data = {}

    for topic, msg, t in bag.read_messages():
        if topic == "/lidar_localizer/aligned_cloud":
            data_array = np.frombuffer(msg.data, dtype=np.uint8)
            point_cloud_data[msg.header.seq] = data_array
        elif topic == "/lidar_localizer/lidar_pose":
            position = msg.pose.pose.position
            orientation = msg.pose.pose.orientation
            lidar_transform_data[msg.header.seq] = [
                position.x, position.y, position.z,
                orientation.x, orientation.y, orientation.z, orientation.w
            ]
    bag.close()

    # Synchronize data based on sequence numbers with an offset
    synced_point_clouds = []
    synced_poses = []

    for seq in point_cloud_data.keys():
        corresponding_pose_seq = seq + seq_offset
        if corresponding_pose_seq in lidar_transform_data:
            synced_point_clouds.append(point_cloud_data[seq])
            synced_poses.append(lidar_transform_data[corresponding_pose_seq])
        else:
            # Handle the case where there is no corresponding pose sequence
            synced_point_clouds.append(point_cloud_data[seq])
            synced_poses.append([np.nan]*7)  # Assuming 7 elements for missing pose data

    point_cloud_data = plot3d_point_clouds(synced_point_clouds, synced_poses)


    '''
    # Organize point clouds into batches
    padded_point_clouds = []
    max_lengths = []

    
    for i in range(0, len(point_cloud_data), batch_size):
        batch = synced_point_clouds[i:i + batch_size]
        max_length = max(len(pc) for pc in batch)
        max_lengths.append(max_length)
        padded_batch = pad_sequences(batch, maxlen=max_length, dtype='uint8', padding='post')
        padded_point_clouds.extend(padded_batch)

    # Log information about the padding and batch processing
    logger.info(f"Processed {len(padded_point_clouds)} point clouds into batches of size {batch_size}")
    for i, ml in enumerate(max_lengths):
        logger.info(f"Batch {i + 1} padded to max length: {ml}")
    #logger.info("After padding:")
    #logger.info("Shape of padded point cloud data: %s", padded_point_clouds.shape)
    #if padded_point_clouds.size > 0:
    #    logger.info("Sample data from the first padded point cloud entry: %s", padded_point_clouds[0][:10])
    '''
    return (point_cloud_data), pd.DataFrame(synced_poses, columns=['pos_x', 'pos_y', 'pos_z', 'ori_x', 'ori_y', 'ori_z', 'ori_w'])

def visualize_results(predicted_points, actual_points):
    logger.info("Predicted LiDAR Points: %s", predicted_points)
    logger.info("Actual LiDAR Points: %s", actual_points)

    # Extract x, y, z coordinates
    x_actual = actual_points[:, 0]
    y_actual = actual_points[:, 1]
    z_actual = actual_points[:, 2]
    x_pred = predicted_points[:, 0]
    y_pred = predicted_points[:, 1]
    z_pred = predicted_points[:, 2]

    # Plotting
    plt.figure(figsize=(18, 6))
    plt.subplot(1, 3, 1)
    plt.scatter(x_actual, x_pred, c='blue')
    plt.title('X Coordinates')
    plt.xlabel('Actual')
    plt.ylabel('Predicted')

    plt.subplot(1, 3, 2)
    plt.scatter(y_actual, y_pred, c='red')
    plt.title('Y Coordinates')
    plt.xlabel('Actual')
    plt.ylabel('Predicted')

    plt.subplot(1, 3, 3)
    plt.scatter(z_actual, z_pred, c='green')
    plt.title('Z Coordinates')
    plt.xlabel('Actual')
    plt.ylabel('Predicted')

    plt.tight_layout()
    plt.show()

    mean_percentage_errors = calculate_mean_percentage_error(actual_points, predicted_points)
    logger.info("Mean Percentage Errors for each element: %s", mean_percentage_errors)

def plot3d_point_clouds(point_clouds, lidar_poses):


    # Ensure the point clouds array is divisible by 3
    reshaped_clouds = []
    for i, cloud in enumerate(point_clouds):
        # Calculate needed padding to make the length of the cloud divisible by 3
        needed_padding = (-len(cloud) % 3)
        if needed_padding:
            cloud = np.pad(cloud, (0, needed_padding), mode='constant')
        if len(cloud) % 3 != 0:
            raise ValueError("The total number of elements in the list must be divisible by 3.")
        
        # Reshape the cloud into 3 columns
        reshaped = cloud.reshape(-1, 3)
        reshaped_clouds.append(reshaped)
    '''
    # Set up the plot for 3D scatter
    fig = plt.figure(figsize=(15, 10))
    ax = fig.add_subplot(111, projection='3d')

    for i in range(len(reshaped_clouds)):
        #if i < len(lidar_poses):
        if i < 3:
            for j in range(len(reshaped_clouds[i])):
                    # Extract x, y, z for plotting
                        print('i:', i, "j:", j, "remaining Js:", len(reshaped_clouds[i])-j)

                        x = reshaped_clouds[i][j][0] + lidar_poses[i][0]
                        y = reshaped_clouds[i][j][1] + lidar_poses[i][1]
                        z = reshaped_clouds[i][j][2] + lidar_poses[i][2]
                        # Plot each point in the point cloud
                        ax.scatter(x,y,z, color='b', alpha=0.5)
                        j += 2

    ax.set_title('Point Clouds X-Y-Z Scatter')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    ax.legend(['Point Clouds'])

    plt.tight_layout()
    plot_filename = os.path.join(current_folder, '3d_point_clouds_plot.png')
    plt.savefig(plot_filename)
    plt.close()
    logger.info("3D Point cloud plots saved to %s", plot_filename)

    # Optionally display the plot
    plt.show()
    '''
    return reshaped_clouds


def plot2d_lidar_positions(actual, predicted):
    plt.figure(figsize=(10, 6))
    for act in actual:
        plt.scatter(act[0], act[1], color='blue', label='Actual' if act is actual[0] else "")  # Only label the first point to avoid duplicate labels
    
    for pred in predicted:
        if pred.ndim > 1 and pred.shape[1] >= 2:  # Ensure pred is at least 2D and has at least two columns
            plt.scatter(pred[0, 0], pred[0, 1], color='red', label='Predicted' if pred is predicted[0] else "")  # pred[0, 0] and pred[0, 1] for first row's x and y
        elif pred.ndim == 1 and len(pred) >= 2:  # If it's 1D but has at least two elements
            plt.scatter(pred[0], pred[1], color='red', label='Predicted' if pred is predicted[0] else "")
        else:
            print(f"Unexpected prediction shape or size: {pred.shape}")

    plt.xlabel('X Coordinate')
    plt.ylabel('Y Coordinate')
    plt.title('2D Lidar Positions')
    plt.legend()

    # Save the plot in the unique folder
    plt.savefig(os.path.join(current_folder, f'lidar_positions.png'))

    plt.show()
    plt.close()  # Close the plot to free up memory

def create_slfn_model(input_shape):
    model = Sequential([
        Dense(64, activation='relu', input_shape=(input_shape,)),
        BatchNormalization(),
        Dense(128, activation='relu'),
        BatchNormalization(),
        Dense(64, activation='relu'),
        BatchNormalization(),
        Dropout(0.2),
        Dense(7, activation='linear')  # Assuming output dimensionality
    ])
    model.compile(optimizer=Adam(learning_rate=0.001), loss='mean_squared_error')
    return model

def manual_split(data, labels, test_ratio=0.15):
    total_samples = len(data)
    split_idx = int(total_samples * (1 - test_ratio))
    X_train, X_test = data[:split_idx], data[split_idx:]
    y_train, y_test = labels[:split_idx], labels[split_idx:]
    return X_train, X_test, y_train, y_test

def adjust_point_cloud_lengths(point_clouds, lidar_poses):
    # Find the shortest point cloud length that is divisible by 3
    min_length = min(len(pc) for pc in point_clouds if len(pc) % 3 == 0)

    adjusted_point_clouds = []
    expanded_poses = []

    # Adjust point clouds and expand poses
    for pc, pose in zip(point_clouds, lidar_poses):
        if len(pc) >= min_length:
            adjusted_point_clouds.append(pc[:min_length])
            # Repeat the pose to match the number of points, then reshape
            repeated_pose = np.repeat([pose], min_length, axis=0)
            # Calculate needed padding to make the total length divisible by 7
            total_elements = repeated_pose.size
            needed_padding = (-total_elements % 7)
            if needed_padding > 0:
                # Pad with zeros (or nan, depending on your data handling needs)
                padded_pose = np.pad(repeated_pose, ((0, 0), (0, needed_padding)), mode='constant', constant_values=np.nan)
                expanded_pose = padded_pose.reshape(-1, 7)
            else:
                expanded_pose = repeated_pose.reshape(-1, 7)
            expanded_poses.append(expanded_pose)

    return adjusted_point_clouds, expanded_poses


def extract_and_adjust_data(bag_file, seq_offset):
    point_clouds, lidar_poses = extract_data_from_bag(bag_file, seq_offset)
    # Adjust point clouds to the shortest one's length and expand poses
    point_clouds, lidar_poses = adjust_point_cloud_lengths(point_clouds, lidar_poses)
    return point_clouds, lidar_poses

def prepare_data_for_training(point_clouds, lidar_poses):
    # Reshape point clouds to (-1, 3) and poses to (-1, 7) and concatenate
    input_data = [np.concatenate([pc.reshape(-1, 3), lp], axis=1) for pc, lp in zip(point_clouds, lidar_poses)]
    input_data = np.vstack(input_data)  # Stack all the data
    return input_data

def train_and_predict(bag_file):
    seq_offset = 25  # Define your offset
    point_clouds, poses = extract_and_adjust_data(bag_file, seq_offset)
    
   # Convert data to numpy arrays for training
    point_clouds = np.array(point_clouds)
    poses = np.array(poses)

    input_data = prepare_data_for_training(point_clouds, poses)

    # Split the data into training and testing sets
    X_train, X_test, y_train, y_test = train_test_split(point_clouds, poses, test_size=0.2)

    # Create model
    input_shape = input_data.shape[1]  # Number of features per sample
    model = create_slfn_model(input_shape)

    # Train the model
    model.fit(X_train, y_train, epochs=10, batch_size=10)

    # Save model
    model.save(os.path.join(current_folder, 'slfn_model.h5'))
    logger.info(f"Model saved to {os.path.join(current_folder, 'slfn_model.h5')}")

    # Evaluate and predict
    predictions = model.predict(X_test)
    plot2d_lidar_positions(predictions, y_test)

train_and_predict('Issue_ID_4_2024_06_13_07_47_15.bag')





train_and_predict('Issue_ID_4_2024_06_13_07_47_15.bag')


#visualize_results(predicted_points, actual_points)




            #THE TWO TOPICS IN THE BAG FILE ARE:
            # /lidar_localizer/lidar_pose                                                               300 msgs    : geometry_msgs/PoseWithCovarianceStamped               
            #/lidar_localizer/aligned_cloud                                                            300 msgs    : sensor_msgs/PointCloud2                               

