import numpy as np
import pandas as pd
import keras
from keras.utils import np_utils
import random
from random import randrange
import os
import shutil
import tensorflow as tf
from keras.datasets import mnist
from keras import backend as K
from keras.preprocessing.image import ImageDataGenerator
from sklearn.model_selection import train_test_split
import cv2

### import packages
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn import preprocessing
import seaborn as sns
 
from sklearn.model_selection import train_test_split, ShuffleSplit, learning_curve, GridSearchCV, KFold, StratifiedKFold
from sklearn.linear_model import LogisticRegression, Perceptron
from sklearn.metrics import roc_curve, accuracy_score, confusion_matrix, classification_report, roc_auc_score, make_scorer, precision_recall_curve, average_precision_score 
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score, cross_val_predict
from sklearn import metrics

from sklearn.ensemble import RandomForestClassifier, IsolationForest, VotingClassifier
from sklearn.neural_network import MLPClassifier

%matplotlib inline
plt.style.use('ggplot')
from sklearn.model_selection import KFold
from itertools import product,chain

from sklearn.naive_bayes import GaussianNB

from sklearn.metrics import recall_score, accuracy_score, confusion_matrix, classification_report
import random
LABELS = ["Normal", "Fraud"]

# Grad-CAM

import keras
import matplotlib.cm as cm
#import tensorflow_datasets as tfds

class DataSource(object):
    def __init__(self):
        raise NotImplementedError()
    def partitioned_by_rows(self, num_workers, test_reserve=.3):
        raise NotImplementedError()
    def sample_single_non_iid(self, weight=None):
        raise NotImplementedError()

class VggFace2(DataSource):
    data_dir = './COVID-19_Radiography_Dataset'

    def padding(self, array, xx, yy):
        """
        :param array: numpy array
        :param xx: desired height
        :param yy: desirex width
        :return: padded array
        """

        h = array.shape[0]
        w = array.shape[1]
        z = 3

        a = (xx - h) // 2
        aa = xx - a - h

        b = (yy - w) // 2
        bb = yy - b - w
        
        l1 = np.pad(array[:,:,0], pad_width=((a, aa), (b, bb)), mode='constant')
        l2 = np.pad(array[:,:,1], pad_width=((a, aa), (b, bb)), mode='constant')
        l3 = np.pad(array[:,:,2], pad_width=((a, aa), (b, bb)), mode='constant')

        return np.stack([l1, l2, l3],axis=2) 

    def __init__(self):
        in_pt, out_pt, ben, target = read_data()

        # Replace values with a binary annotation
        ben = ben.replace({'ChronicCond_Alzheimer': 2, 'ChronicCond_Heartfailure': 2, 'ChronicCond_KidneyDisease': 2,
                        'ChronicCond_Cancer': 2, 'ChronicCond_ObstrPulmonary': 2, 'ChronicCond_Depression': 2,
                        'ChronicCond_Diabetes': 2, 'ChronicCond_IschemicHeart': 2, 'ChronicCond_Osteoporasis': 2,
                        'ChronicCond_rheumatoidarthritis': 2, 'ChronicCond_stroke': 2, 'Gender': 2 }, 
                        0)
        ben = ben.replace({'RenalDiseaseIndicator': 'Y'}, 1).astype({'RenalDiseaseIndicator': 'int64'})
        # Change target variable to binary
        target["target"] = np.where(target.PotentialFraud == "Yes", 1, 0) 
        target.drop('PotentialFraud', axis=1, inplace=True)

        # Merge in_pt, out_pt and ben df into a single patient dataset
        data = pd.merge(in_pt, out_pt,
                    left_on = [ idx for idx in out_pt.columns if idx in in_pt.columns],
                    right_on = [ idx for idx in out_pt.columns if idx in in_pt.columns],
                    how = 'outer').\
        merge(ben,left_on='BeneID',right_on='BeneID',how='inner')

        patient_merge_id = [i for i in out_pt.columns if i in in_pt.columns]
        # Merge in_pt, out_pt and ben df into a single patient dataset
        data = pd.merge(in_pt, out_pt,
                    left_on = patient_merge_id,
                    right_on = patient_merge_id,
                    how = 'outer').\
        merge(ben,left_on='BeneID',right_on='BeneID',how='inner')

        # We find the number of unique physicians 
        data['N_unique_Physicians'] = N_unique_values(data[['AttendingPhysician', 'OperatingPhysician', 'OtherPhysician']]) 
        # We separate the types of physicians into numeric values
        data[['AttendingPhysician', 'OperatingPhysician', 'OtherPhysician']] = np.where(data[['AttendingPhysician','OperatingPhysician',
                                                                                            'OtherPhysician']].isnull(), 0, 1)
        # We count the number of types of physicians that attend the patient
        data['N_Types_Physicians'] = data['AttendingPhysician'] +  data['OperatingPhysician'] + data['OtherPhysician']
        # Now we create a variable to check if there is a single doctor on a patient that was attended by more than 1 type of doctor
        # This helps us finds those cases that are only looked at by 1 physicians
        data['Same_Physician'] = data.apply(lambda x: 1 if (x['N_unique_Physicians'] == 1 and x['N_Types_Physicians'] > 1) else 0,axis=1)
        # Similar to Same_Physician, we create a variable to see if 1 physicians has had multiple roles, but has not been alone reviewing the case
        data['Same_Physician2'] = data.apply(lambda x: 1 if (x['N_unique_Physicians'] == 2 and x['N_Types_Physicians'] > 2) else 0,axis=1)
        # We check our new variables
        data[['N_unique_Physicians','N_Types_Physicians','Same_Physician','Same_Physician2']].head()

        # We count the number of procedures for each claim, we drop the initial variables
        ClmProcedure_vars = ['ClmProcedureCode_{}'.format(x) for x in range(1,7)]
        data['N_Procedure'] = N_unique_values(data[ClmProcedure_vars])
        data = data.drop(ClmProcedure_vars, axis = 1)
        # We count the number of claims, we also separate this by unique claims and extra claims, we drop the initial variables
        ClmDiagnosisCode_vars =['ClmAdmitDiagnosisCode'] + ['ClmDiagnosisCode_{}'.format(x) for x in range(1, 11)]
        data['N_Unique_Claims'] = N_unique_values(data[ClmDiagnosisCode_vars])
        data['N_Total_Claims'] = data[ClmDiagnosisCode_vars].notnull().to_numpy().sum(axis = 1)
        data['N_Extra_Claims'] = data['N_Total_Claims'] - data['N_Unique_Claims']
        ClmDiagnosisCode_vars.append('N_Total_Claims')
        data = data.drop(ClmDiagnosisCode_vars, axis = 1)

        #  Transform string columns of date into type date
        data['AdmissionDt'] = pd.to_datetime(data['AdmissionDt'] , format = '%Y-%m-%d')
        data['DischargeDt'] = pd.to_datetime(data['DischargeDt'],format = '%Y-%m-%d')
        data['ClaimStartDt'] = pd.to_datetime(data['ClaimStartDt'] , format = '%Y-%m-%d')
        data['ClaimEndDt'] = pd.to_datetime(data['ClaimEndDt'],format = '%Y-%m-%d')
        data['DOB'] = pd.to_datetime(data['DOB'] , format = '%Y-%m-%d')
        data['DOD'] = pd.to_datetime(data['DOD'],format = '%Y-%m-%d')
        # Number of days
        data['Admission_Days'] = ((data['DischargeDt'] - data['AdmissionDt']).dt.days) + 1
        # Number of claim days 
        data['Claim_Days'] = ((data['ClaimEndDt'] - data['ClaimStartDt']).dt.days) + 1
        # Age at the time of claim
        data['Age'] = round(((data['ClaimStartDt'] - data['DOB']).dt.days + 1)/365.25)

        # We create a Hospitalization flag 
        data['Hospt'] = np.where(data.DiagnosisGroupCode.notnull(), 1, 0)
        data = data.drop(['DiagnosisGroupCode'], axis = 1)
        # Variable if patient is dead
        data['Dead']= 0
        data.loc[data.DOD.notna(),'Dead'] = 1

        data['Missing_Deductible_Amount_Paid'] = 0
        data.loc[data['DeductibleAmtPaid'].isnull(), 'Missing_Deductible_Amount_Paid'] = 1 
        data = data.fillna(0).copy()

        _sum = data.groupby(['Provider'], as_index = False)[['InscClaimAmtReimbursed', 'DeductibleAmtPaid', 'RenalDiseaseIndicator', 
                                                    'ChronicCond_Alzheimer', 'AttendingPhysician', 'OperatingPhysician', 
                                                    'OtherPhysician', 'N_unique_Physicians', 'ChronicCond_Heartfailure', 
                                                    'N_Types_Physicians', 'Same_Physician',
                                                    'ChronicCond_KidneyDisease', 'ChronicCond_Cancer', 
                                                    'ChronicCond_ObstrPulmonary', 'ChronicCond_Depression', 
                                                    'ChronicCond_Diabetes', 'ChronicCond_IschemicHeart', 
                                                    'ChronicCond_Osteoporasis', 'ChronicCond_rheumatoidarthritis',
                                                    'ChronicCond_stroke', 'Dead', 
                                                    'N_Procedure','N_Unique_Claims', 'N_Extra_Claims', 'Admission_Days',
                                                    'Claim_Days', 'Hospt', 'Missing_Deductible_Amount_Paid']].sum()

        # To separate our variables, we shall add '_sum' at the end of their names
        _sum = _sum.add_suffix('_sum')
        ### Count number of records
        _count = data[['BeneID', 'ClaimID']].groupby(data['Provider']).nunique().reset_index()
        _count.rename(columns={'BeneID':'BeneID_count','ClaimID':'ClaimID_count'},inplace=True)
        ### Calculate mean for all numeric variables
        _mean = data.groupby(['Provider'], as_index = False)[['NoOfMonths_PartACov', 'NoOfMonths_PartBCov',
                                                            'IPAnnualReimbursementAmt', 'IPAnnualDeductibleAmt',
                                                            'OPAnnualReimbursementAmt', 'OPAnnualDeductibleAmt', 'Age',
                                                            'AttendingPhysician', 'OperatingPhysician','OtherPhysician',
                                                            'N_unique_Physicians', 'ChronicCond_Heartfailure', 
                                                            'N_Types_Physicians', 'Same_Physician',
                                                            'ChronicCond_KidneyDisease', 'ChronicCond_Cancer', 
                                                            'ChronicCond_ObstrPulmonary', 'ChronicCond_Depression', 
                                                            'ChronicCond_Diabetes', 'ChronicCond_IschemicHeart', 
                                                            'ChronicCond_Osteoporasis', 'ChronicCond_rheumatoidarthritis',
                                                            'ChronicCond_stroke', 'Dead', 'N_Procedure','N_Unique_Claims', 
                                                            'N_Extra_Claims', 'Admission_Days','Claim_Days', 'Hospt',
                                                            'Missing_Deductible_Amount_Paid'
                                                        ]].mean()
        # To separate our variables, we shall add '_mean' at the end of their names
        _mean = _mean.add_suffix('_mean')
        # We create a dataset that holds all the variables
        _total = _count.merge(_sum, how='left',left_on='Provider',right_on='Provider_sum').\
                        merge(_mean, how='left',left_on='Provider',right_on='Provider_mean').\
                        drop(['Provider_sum','Provider_mean'], axis=1).\
                        merge(target, on='Provider', how='left')

        df = _total[['InscClaimAmtReimbursed_sum','N_Extra_Claims_sum','Claim_Days_sum',
             'AttendingPhysician_mean','Missing_Deductible_Amount_Paid_mean','Dead_mean','Claim_Days_mean','N_Extra_Claims_mean',
             'BeneID_count','ClaimID_count',
             'Provider','target']]

        test = df.sample(frac=0.3)
        all_data = df.sample(frac=0.2)
        train, validate = all_data.sample(frac=0.8), all_data.sample(frac=0.2)

        self.train = train
        self.test = test
        self.valid = validate
        #self.y_train = labels_test

    def fake_non_iid_data(self, min_train=100, max_train=1000, data_split=(.6,.3,.1)):
        return ((self.train, self.test, self.valid), [1]) 
    
if __name__ == "__main__":
    m = VggFace2()
    print(m)
    # res = m.partitioned_by_rows(9)
    # print(res["test"][1].shape)
    #for _ in range(10):
        #print(m.gen_dummy_non_iid_weights())

def read_data(tp = "Train", N = 1542865627584):
    target = pd.read_csv("./{}-{}.csv".format(tp.title(), N))
    pt = pd.read_csv("./{}_Beneficiarydata-{}.csv".format(tp.title(), N))
    in_pt = pd.read_csv("./{}_Inpatientdata-{}.csv".format(tp.title(), N))
    out_pt = pd.read_csv("./{}_Outpatientdata-{}.csv".format(tp.title(), N))
    return (in_pt, out_pt, pt, target)
def N_unique_values(df):
    return np.array([len(set([i for i in x[~pd.isnull(x)]])) for x in df.values])