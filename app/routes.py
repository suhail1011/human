import ipdb
from flask import request, jsonify, render_template, redirect, url_for, flash, Response, send_file, send_from_directory
from flask.logging import create_logger
from requests_toolbelt import MultipartEncoder
import pandas as pd
from app import app
from app import api
from app import ap_parser
from app.db import get_db
from app import user_handler
from app import login_handler
from app import error_handler
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, logout_user, login_user, login_required, current_user
from datetime import timedelta
import json
import os
import logging
from collections import Counter

# for flask run
app.logger = create_logger(app)

# when running gunicorn
# gunicorn_logger = logging.getLogger('gunicorn.error')
# app.logger = gunicorn_logger

## API routes
# Add custom api routes here. Be careful not to overwrite other routes or route function names.
#####################################




#####################################


@app.route('/api/callAPI', methods=["POST", "OPTIONS"])
def call_api():
    """
    Passthrough for calling functions from api.
    The name of the function is given as a api_call attribute in json payload

    For further information how to use this see api.py
    """
    if not request.is_json:
        return "Unexpected Parameters"
    req = request.get_json()
    # get api function and remove api_call from arguments
    api_call = getattr(api, req.pop('api_call'))
    # call api function with all other json attributes as arguments
    resp = api_call(**req)
    return jsonify(resp)

@app.route('/api/getdatafile', methods=["GET"])
def choose_file():
    """
    This function automatically chooses and returns unannotated data for the current user 
    including a file. The path of this file is found in the content field of the database.
    """
    # call choose_text and get a piece of data
    chosen = choose_text()
    # if something went wrong in choose_text then pass through the string
    if chosen and not isinstance(chosen, str):
        data = chosen.json
    else:
        return chosen
    app.logger.debug(data)
    # return a multipart encoded form with data being the fields from the line of the database
    # and file being the file which is found at the path where content field leads to.
    datafile = "./uploaded_files/"+data['content']
    if not '..' in data['content']:
        if os.path.exists(os.path.realpath(datafile)):
            multipart = MultipartEncoder(fields={'data': json.dumps(data),
                                                'file': (datafile, open(datafile, 'rb'))
                                                })
        else:
            return "File " + datafile +  "does not exit. Please contact your admin."
    else:
        return "Filepaths with /../ are not allowed. Please contact your admin."
    return (multipart.to_string(), {'Content-Type': multipart.content_type})

@app.route('/api/getdata', methods=["GET", "POST", "OPTIONS"])
def choose_text():
    """
    This function automatically chooses and returns a piece of unannotated 
    data for the current user
    """
    uid = current_user.get_id()

    db = get_db()

    row = db.execute('SELECT max_annotations FROM options').fetchone()
    max_annotations = int(row['max_annotations'])
    
    # get user from database
    user = db.execute(
        'SELECT * FROM user WHERE id = ?', (uid,)
        ).fetchone() 
    if user is None:
        return 'User not found'
    # if nothing annotated return first in list
    if user['annotated'] is None:
        selected = db.execute(
            'SELECT * FROM data', ()
        ).fetchone()
        if selected is not None:
            return jsonify(row2dict(selected))
        else:
            return 'No available data'
    else:
        annotated = user['annotated'].split()
    # select all the id which have less than max_annotations
    annotation_list = db.execute('SELECT annotated FROM user').fetchall()
    annotation_count = []

    for item in annotation_list:
        try:
            annotation_by_individual_user = item[0].split()
            annotation_count.extend(annotation_by_individual_user)
        except Exception as e:
            app.logger.error("Exception occurred:"+str(e))
            pass

    annotation_count_dict = Counter(annotation_count)

    #retrieve all the annotations higher than max_annotations
    already_sufficient_count = [k for (k,v) in annotation_count_dict.items() if v>=max_annotations]
    # add already_sufficient_count to annotated

    annotated.extend(annotation_count_dict)

    # select first which was not annotated yet. join adds '?' dynamically
    query = 'SELECT * FROM data WHERE id NOT IN ({})'.format(','.join('?'*len(annotated))) 
    selected = db.execute(
        query, (annotated)
        ).fetchone()
    # return selected
    if selected is not None:
        return jsonify(row2dict(selected))
    else:
        return 'No available data'

@login_required
@app.route('/api/write_to_db', methods=["POST", "OPTIONS"])
def write_to_db():
    """
    This function writes the completed annotations a user did to the database
    """
    if not request.is_json:
        return "Unexpected Parameters"
    data = request.get_json()
    data['user'] = current_user.get_id()
    print(data)
    if str(data['id']) in current_user.get_annotated().split():
        raise  error_handler.DatabaseError("Already annotated", 500)
    # try:
    db = get_db()
    cursor = db.execute('select * from annotations')
    allowed_columns = [d[0] for d in cursor.description]
    for key, v in list(data.items()):
        if key not in allowed_columns:
            del data[key]
        else:
            data[key] = str(v)
    db.execute(
        'INSERT INTO annotations ({0}) VALUES ({1})'.format(
            ', '.join(('"'+str(key)+'"' for key in data)),
            ', '.join(('?' for key in data))
        ),
        tuple((data[key]) for key in data)
    )
    db.execute(
        'UPDATE user set annotated = ? WHERE id = ?',
        (" ".join([current_user.get_annotated(), str(data['id'])]), current_user.get_id())
    )
    
    db.commit()
    return 'Success'

@app.route('/login', methods=["GET", "POST"])
def login():
    """
    Function to display the login page and handle user logins
    """
    app.logger.debug("Entered login method -- login()")
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user, error = user_handler.authenticate_login(username, password)
        if user is None:
            app.logger.debug("user-None")
            return render_template('login.html', error=error)
        login_user(user, remember=False, duration=timedelta(minutes=30))
        app.logger.debug("Current User: {}".format(current_user.fname))
        app.logger.debug("User logged in successfully")
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/register_user', methods=["GET", "POST"])
def register_user_frontend():
    """
    Function to display the registration page and also handle user registration request.
    """
    app.logger.debug("Requested for new user registration -- register_user")
    success, failure = None, None
    if request.method == 'POST':
        fname = request.form['fname']
        lname = request.form['lname']
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        app.logger.debug("Requested resource: fname:{} lname: {} email:{}, username:{}, password:{}, confirm_passowrd:{}".format(
                         fname, lname, email, username, password, confirm_password))
        success, failure = user_handler.register_user(username, email, fname, lname, password, confirm_password)
        app.logger.debug("Success message:{}".format(success if success else "None"))
        app.logger.debug("Failure message:{}".format(failure if failure else "None"))    
        
        if success:
            app.logger.info("User {} added succesfully".format(username))
            return render_template('login.html',success=success, user=username)
    
    return render_template('register_user.html', error = failure)


@app.route('/upload_console', methods=["GET"])
@login_required
def upload_console():
    """
    Function to load upload console, contains options to upload files and folders.
    """
    app.logger.debug("Requested file/folder upload console")
    ## Verify if the logged in user is admin
    if not current_user.admin:
        app.logger.info("upload_file requested by non-admin user")
        return render_template('login.html',error="login as admin to proceed")
    annotations=get_annotations()
    annotations = annotations.to_dict(orient='records')
    data = get_data()
    data = data.to_dict(orient="records")
    return render_template('upload_console.html',success=request.args.get('success'),
                    error=request.args.get('error'),admin=current_user.admin,user=current_user.fname, annotations=annotations, data=data)

@app.route("/data_console", methods=["GET"])
@login_required
def data_console():
    "Function to display data such as annotations and 'data'"

    app.logger.debug("Requested data view")

    ## Verify if the logged in user is admin
    if not current_user.admin:
        app.logger.info("upload_file requested by non-admin user")
        return render_template('login.html',error="login as admin to proceed")
    annotations=get_annotations()
    annotations = annotations.to_dict(orient='records')
    data = get_data()
    data = data.to_dict(orient="records")
    return render_template('data_console.html',success=request.args.get('success'),
                    error=request.args.get('error'), admin=current_user.admin, user=current_user.fname, annotations=annotations, data=data)

@app.route('/upload_file', methods=["GET", "POST"])
@login_required
def upload_file():
    """
    Function to upload the annotation file to the tool.
    (Uploading of the file to be restricted to the admin.)
    """

    app.logger.debug("Requested file upload page")
    ## Verify if the logged in user is admin
    if not current_user.admin:
        app.logger.info("upload_file requested by non-admin user")
        return render_template('login.html',error="login as admin to proceed")

    if request.method == 'POST':
        files = request.files.getlist('files[]')
        
        app.logger.info("Files: " + str(files))
        ## Handling Zero inputs
        if len(files) == 1:
            if files[0].filename == '':
                app.logger.info("Submitted 0 (zero) files")
                return render_template('upload_console.html', error=str("Upload atleast one file"), 
                                       user=current_user.fname, admin=current_user.admin)
        
        # Save the files on the server.
        for file_ in files:
            file_.save('uploaded_files/'+secure_filename(file_.filename))

        # Process files and save in DB
        db = get_db()
        failed_files = ""
        success_files = 0
        try:
            id_list = db.execute('SELECT id FROM data').fetchall()

            init_id = 0
            for i in id_list:
                if int(i[0]) > init_id:
                    init_id = int(i[0])

            app.logger.debug('from: upload_file: init_id:{}; len_list:{}'
                             .format(init_id, len(id_list)))

        except Exception as e:
            app.logger.critical('Exception occurred while processing the database while uploading the file:'+str(e))
            raise error_handler.UnknownError(e)
            
        for file_ in files:
            try:
                df = pd.read_csv('uploaded_files/'+secure_filename(file_.filename), 
                                 sep='\t', header=0, names=['content', 'context', 'meta'])

                for index, row in df.iterrows():
                    init_id += 1
                    db.execute('INSERT INTO data (id, content, context, meta) VALUES (?, ?, ?, ?)',
                               (init_id, row['content'], row['context'], row['meta']))

                db.commit()
                success_files += 1
            except Exception as e:
                failed_files += file_.filename+" "
                app.logger.error("Exception occurred while processing the database while uploading the file:"+str(e))

        if failed_files != "":
            app.logger.error("Failed to upload one or more files:"+str(failed_files))
            if success_files == 0:
                return render_template('upload_console.html', error=str("Error uploading the files: "+failed_files), 
                                       user=current_user.fname, admin=current_user.admin)
            else:
                return render_template('upload_console.html', error=str("Error uploading the files: "+failed_files), 
                                       success=str(success_files)+" files uploaded successfully", user=current_user.fname, admin=current_user.admin)

        app.logger.info("Files uploaded successfully:" + str(success_files))
        return render_template('upload_console.html', success=str(success_files)+" files uploaded successfully", 
                               user=current_user.fname, admin=current_user.admin)
    else:
        app.logger.debug("from upload_file current User:{}".format(current_user.fname))
        return render_template('upload_console.html', user=current_user.fname, admin=current_user.admin)

@app.route('/upload_folder', methods=["GET", "POST"])
@login_required
def upload_folder():
    """
    Function to upload the data folder to the tool.
    (Uploading of the file to be restricted to the admin.)
    """

    app.logger.debug("Requested folder upload page")
    ## Verify if the logged in user is admin
    if not current_user.admin:
        app.logger.info("upload_file requested by non-admin user")
        return render_template('login.html',error="login as admin to proceed")

    if request.method == 'POST':
        folder = request.files.getlist('folder')
        app.logger.info("Folders: " + str(folder))
        
        ## Handling Zero inputs
        if len(folder) == 1:
            if folder[0].filename == '':
                app.logger.info("Submitted 0 (zero) folder")
                return render_template('upload_folder.html', error=str("Upload atleast one folder"), 
                                       user=current_user.fname, admin=current_user.admin)

        #Check if the folder exists
        try:
            os.makedirs(os.path.join('uploaded_files/', '/'.join([subdir for subdir in folder[0].filename.split('/')[:-1]])), exist_ok=False)
        except Exception as e:
            app.logger.info("Folder already exists")
            app.logger.info("Error: "+str(e))
            return render_template('upload_console.html', error=str("Folder already exists"), user=current_user.fname, admin=current_user.admin)

        failed_files = ""
        success_files = 0
        # Save the folder on the server.

        for file_ in folder:
            # Create the directory by eliminating the file name in the path
            try:
                os.makedirs(os.path.join('uploaded_files/', '/'.join([subdir for subdir in file_.filename.split('/')[:-1]])), exist_ok=True)
                file_.save('uploaded_files/'+file_.filename)
                success_files += 1
            except Exception as e:
                app.logger.error("Error uploading file from the folder: "+str(e))
                failed_files += str(file_.filename)+" "

        
        if failed_files != "":
            app.logger.error("Failed to upload one or more files:"+str(failed_files))
            if success_files == 0:
                return render_template('upload_console.html', error=str("Error uploading the files: "+failed_files), user=current_user.fname, admin=current_user.admin)
            else:
                return render_template('upload_console.html', error=str("Error uploading the files: "+failed_files), success=str(success_files)+" files uploaded successfully", user=current_user.fname, admin=current_user.admin)

        app.logger.info("Files uploaded successfully:" + str(success_files))
        return render_template('upload_console.html', success=str(success_files)+" files uploaded successfully",user=current_user.fname, admin=current_user.admin)
    
    ## GET request
    app.logger.debug("from upload_file current User:{}".format(current_user.fname))
    return render_template('upload_console.html', user=current_user.fname, admin=current_user.admin)

@app.route('/data_download', methods=["GET", "POST"])
@login_required
def data_download():
    """
    Download data in database after converting it to csv/tsv.
    (Downloading of the data to be restricted to the admin.)
    """

    app.logger.debug("Requested dowload page")
    ## Verify if the logged in user is admin
    if not current_user.admin:
        app.logger.info("data_downloaded requested by non-admin user")
        return render_template('login.html',error="login as admin to proceed")

    if request.method == 'POST':
        try:
            os.makedirs('download_data/', exist_ok=False)
        except Exception as e:
            app.logger.info("Folder already exists")
        try:
            db = get_db()
            df = pd.read_sql_query("SELECT * FROM annotations", db)
            df.to_json('download_data/Annotation_comparisons.json')
            df.to_csv('download_data/annotations.csv', index_label='index', sep=";")
            df = pd.read_sql_query("SELECT * FROM user", db)
            print(df)
            df.to_csv('download_data/user.csv', index_label='index', sep=";")
            df = pd.read_sql_query("SELECT * FROM data", db)
            print(df)
            df.to_csv('download_data/data.csv', index_label='index', sep=";")
        except Exception as e:
            app.logger.error("Database Error:"+str(e))
            raise error_handler.DatabaseError(str(e))
        try:
            annotation_df = pd.read_csv('download_data/annotations.csv',sep=';',encoding='utf-8',header=0)
            users_df = pd.read_csv('download_data/user.csv',sep=';',encoding='utf-8',header=0)
            data_df = pd.read_csv('download_data/data.csv',sep=';',encoding='utf-8',header=0)

            users_dict = pd.Series(users_df.given_name.values,index=users_df.id).to_dict()
            comments_dict = pd.Series(data_df.content.values,index=data_df.id).to_dict()

            annotation_df.insert(loc=1,column='Name',value=annotation_df['user'].map(users_dict))
            annotation_df.insert(loc=1,column='Instance',value=annotation_df['id'].map(comments_dict))

            annotation_df = annotation_df.sort_values(by=['id','Name'])
            annotation_df.drop(['user'],inplace=True,axis=1)

            try:
                annotation_df.to_excel('download_data/Annotation_comparisions.xlsx')
                return send_file('../download_data/Annotation_comparisions.xlsx',as_attachment=True)

            except ImportError as e:
                annotation_df.to_csv('download_data/Annotation_comparisions.csv')
                return send_file('../download_data/Annotation_comparisions.csv',as_attachment=True)
        except Exception as e:
            app.logger.error("Error:"+str(e))
            raise error_handler.UnknownError(str(e))
    return render_template('upload_console.html', user=current_user.fname, admin=current_user.admin)


@app.route('/profile', methods=["GET"])
@login_required
def load_profile():
    """
    Function to load a profile to display it for admin
    """
    app.logger.debug("from load_profile admin user:{}".format(current_user.admin))
    app.logger.debug("from load_profile current user:{}".format(current_user.admin))
    uid = current_user.get_id()

    db = get_db()
    annotations = db.execute(
        'SELECT annotated FROM user WHERE id = ?', (uid,)
        ).fetchone()
    try:
        annotation_by_individual_user = len(annotations[0].split())
    except Exception as e:
        app.logger.error("Exception:"+str(e))
        annotation_by_individual_user = 0
    # get user from database

    return render_template('profile.html', fname=current_user.fname, lname=current_user.lname, 
                           username=current_user.username, user_type=current_user.user_type, 
                           email=current_user.email, user=current_user.fname, 
                           admin=current_user.admin, annotation_by_individual_user = annotation_by_individual_user)

@app.route('/api/changePassword', methods=["GET", "POST"])
@login_required
def change_password():
    """
    Function to change the user password.
    returns to the same page with "Success or Failure Message"
    """
    app.logger.debug("from load_profile admin user:{}".format(current_user.username))
    success, failure = None, None
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        new_password = request.form['new_password']
        confirm_new_password = request.form['confirm_new_password']
        app.logger.debug("Requested resource: password:{} confirm_password: {} new_password:{}, confirm_new_password:{}".format(
                         password, confirm_password, new_password, confirm_new_password))
        success, failure = user_handler.change_password(current_user.username, password, 
                                                        confirm_password, new_password,
                                                        confirm_new_password)
        app.logger.debug("Success message:{}".format(success if success else "None"))
        app.logger.debug("Failure message:{}".format(failure if failure else "None"))
    return render_template('changePassword.html', user=current_user.fname, 
                           admin=current_user.admin, success = success, error = failure)

@app.route('/adminConsole', methods=["GET", "POST"])
@login_required
def admin_console():
    """
    Function that gives access to the admin console.
    Access should be restricted only to the admins.

    Actions that can be further performed by the admin through this console:
        1. activate or deactivate a user.
        2. change password for the user.
    """
    app.logger.debug("from admin_console")
    ## Verify if the logged in user is a admin user
    if not current_user.admin:
        app.logger.info("the user {} is not admin".format(current_user))
        return render_template('login.html', error="login as admin to proceed")

    db = get_db()

    df = pd.read_sql_query('select * from user', db)
    ## Fetch all non-admin users. Admin users shoudln't be modified by other admin
    df = df[df['user_type']!='admin']

    active_users = df[df['is_approved'] == 'yes']
    inactive_users = df[df['is_approved'] == 'no']


    if request.method == 'POST':
        username = request.form['user_select']
        user1 = login_handler.load_user_by_name(username)
        app.logger.debug("Selected user object: {}".format(user1))
        app.logger.debug("Selected user fname: {}".format(user1.fname))
        annotations = db.execute(
        'SELECT annotated FROM user WHERE id = ?', (user1.get_id(),)
        ).fetchone()
        try:
            annotation_by_individual_user = len(annotations[0].split())
        except Exception as e:
            app.logger.error("Exception:"+str(e))
            annotation_by_individual_user = 0
        return render_template('adminConsole.html', user=current_user.fname, admin=current_user.admin, 
                               active_users=active_users['username'], inactive_users=inactive_users['username'],
                               all_users=df['username'], fname=user1.fname, lname=user1.lname, username=user1.username,
                               user_type=user1.user_type, email=user1.email, active_account=user1.is_approved,annotation_by_individual_user=annotation_by_individual_user)

    return render_template('adminConsole.html', user=current_user.fname, admin=current_user.admin,
                           active_users=active_users['username'], inactive_users=inactive_users['username'],
                           all_users=df['username'],success=request.args.get('success'),
                           error=request.args.get('failure'))

@app.route('/options', methods=["GET", "POST"])
@login_required
def change_options():
    """
    Function that gives access to the admin console.
    Access should be restricted only to the admins.

    Actions that can be further performed by the admin through this console:
        1. activate or deactivate a user.
        2. change password for the user.
    """
    app.logger.debug("from options")
    ## Verify if the logged in user is a admin user
    if not current_user.admin:
        app.logger.info("the user {} is not admin".format(current_user))
        return render_template('login.html', error="login as admin to proceed")

    success, failure = "",""
    db = get_db()

    row = db.execute('SELECT max_annotations FROM options').fetchone()
    max_annotations = row['max_annotations']

    app.logger.debug("max_annotations in database: "+str(max_annotations))

    if request.method == 'POST':
        max_annotations = request.form['max_annotations']
        try:
            max_annotations = int(max_annotations)
        except Exception as e:
            app.logger.error("max_annotations entered is not integer")
            return render_template('options.html', user=current_user.fname, admin=current_user.admin, error = failure)

        app.logger.debug("max_annotations: {}".format(max_annotations))

        try:
            db.execute('UPDATE options set max_annotations = ?',(max_annotations,))
            db.commit()
            success = "Successfully changed Maximum annotations per data item: {}".format(max_annotations)
        except Exception as e:
            app.logger.error("Exception occurred : {}".format(str(e)))
            app.logger.error("rolling back DB")
            db.rollback()
            app.logger.error("Error occurred while updating option, DB rolled-back")
            raise error_handler.DatabaseError(str(e))
        return render_template('options.html', user=current_user.fname, admin=current_user.admin, max_annotations=int(max_annotations), success=success)

    return render_template('options.html', user=current_user.fname, admin=current_user.admin, max_annotations=int(max_annotations))

@app.route('/api/activate_user', methods=["POST"])
@login_required
def activate_user():
    """
    Activate the user by calling the method in user_handler
    """
    app.logger.debug("from activate_user")
    db = get_db()

    username = request.form['user_select']

    app.logger.debug("Requested username {}".format(username))
    success, failure = user_handler.activate_user(username)

    app.logger.debug("Success message:{}".format(success if success else "None"))
    app.logger.debug("Failure message:{}".format(failure if failure else "None"))
  
    return redirect(url_for('admin_console', success=success, failure=failure))

@app.route('/api/deactivate_user',methods=["POST"])
@login_required
def deactivate_user():
    """
    Dectivate the user by calling the method in user_handler
    """
    app.logger.debug("from deactivate_user")
    db = get_db()

    username = request.form['user_select']
    app.logger.debug("Requested username {}".format(username))

    success, failure = user_handler.deactivate_user(username)
    app.logger.debug("Success message:{}".format(success if success else "None"))
    app.logger.debug("Failure message:{}".format(failure if failure else "None"))
    return redirect(url_for('admin_console', success=success, failure=failure))

@app.route('/api/change_password_admin', methods=["POST"])
@login_required
def change_password_admin():
    """
    Change the password for normal user by calling the method in user_handler. 
    (Action performed by the admin on behalf of other user)
    """
    app.logger.debug("from change_password_user")
    db = get_db()
    username = request.form['user_select']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    admin_password = request.form['admin_password']

    admin_username = current_user.username
    success, failure = user_handler.change_password_admin(username, password, confirm_password,
                                                          admin_username, admin_password)
    app.logger.debug("Success message:{}".format(success if success else "None"))
    app.logger.debug("Failure message:{}".format(failure if failure else "None"))
    return redirect(url_for('admin_console', success=success, failure=failure))


@app.route('/logout')
@login_required
def logout():
    """
    Function to logout the user
    """
    app.logger.debug("from logout()")
    logout_user()
    app.logger.info("User logged out")
    return redirect(url_for('login'))

## Template routes

@app.route('/')
@login_required
def home():
    """
    Route for home page
    """
    app.logger.debug("from / (home_page)")
    return render_template('annotation_page.html', user=current_user.fname, admin=current_user.admin)


########## MISC Functions

def row2dict(row):
    '''
    Converts a SQLite row to a dict
    '''
    dic = {}
    for column in row.keys():
        dic[column] = row[column]
    return dic



def get_annotations() -> pd.DataFrame:
    """
    Read annotations in database and return them as a Dataframe
    """
    try:
        db = get_db()
        df_annotations = pd.read_sql_query("SELECT * FROM annotations", db)
        df_data = pd.read_sql_query("SELECT * FROM data", db)
    except Exception as e:
        app.logger.error("Database Error:"+str(e))
        raise error_handler.DatabaseError(str(e))
    try:

        comments_dict = pd.Series(df_data.content.values,index=df_data.id).to_dict()

        df_annotations.insert(loc=1,column='comment',value=df_annotations['data_id'].map(comments_dict))

        df_annotations = df_annotations.sort_values(by=['id'])
        #df_annotations.drop(['user'],inplace=True,axis=1)
        return df_annotations
    except Exception as e:
        app.logger.error("Error:"+str(e))
        raise error_handler.UnknownError(str(e))

def get_data() -> pd.DataFrame:
    """
    Read data in database and return them as a DataFrame
    """

    try:
        db = get_db()
        df_data = pd.read_sql_query("SELECT * FROM data", db)

        df_annotations_per_data = pd.read_sql_query("SELECT data_id, COUNT(*) FROM annotations GROUP BY data_id", db)
    except Exception as e:
        app.logger.error("Database Error:" + str(e))
        raise error_handler.DatabaseError(str(e))

    try:
        annotations_per_data_dict = pd.Series(df_annotations_per_data.get("COUNT(*)").values, index = df_annotations_per_data.data_id).to_dict()
        df_data.insert(loc=1, column="annotations", value=df_data["id"].map(annotations_per_data_dict))
        df_data.fillna({"annotations": 0}, inplace=True) #TODO restrict to annotations column
        df_data.annotations = df_data.annotations.astype(int)
        df_data = df_data.sort_values(by=['id'])
        return df_data
    except Exception as e:
        app.logger.error("Error:" + str(e))
        raise error_handler.UnknownError(str(e))
