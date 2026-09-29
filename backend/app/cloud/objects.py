"""Private S3-compatible storage. The bucket must deny public access."""
import io
import os
import uuid
import zipfile
from pathlib import Path
from .db import namespace


def client():
    import boto3
    from botocore.config import Config
    return boto3.client('s3', endpoint_url=os.environ.get('STEVENS_S3_ENDPOINT_URL') or None,
        region_name=os.environ.get('STEVENS_S3_REGION', 'us-east-1'),
        aws_access_key_id=os.environ['STEVENS_S3_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['STEVENS_S3_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4', retries={'max_attempts':3}, connect_timeout=10, read_timeout=60))


def bucket(): return os.environ['STEVENS_S3_BUCKET']
def prefix(sid): return f'{namespace()}/sessions/{sid}/'
def put(key, data, content_type='application/octet-stream'):
    client().put_object(Bucket=bucket(), Key=key, Body=data, ContentType=content_type)
    return key
def get(key): return client().get_object(Bucket=bucket(), Key=key)['Body'].read()
def remove(key): client().delete_object(Bucket=bucket(), Key=key)


def snapshot(sess):
    stream = io.BytesIO()
    root = Path(sess.dir).resolve()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob('*'):
            if path.is_file() and not path.is_symlink():
                archive.write(path,path.relative_to(root).as_posix())
    return put(prefix(sess.id)+'snapshots/'+uuid.uuid4().hex+'.zip',stream.getvalue())


def restore(key, directory):
    root=Path(directory).resolve();root.mkdir(parents=True,exist_ok=True)
    if not key: return
    with zipfile.ZipFile(io.BytesIO(get(key))) as archive:
        if sum(x.file_size for x in archive.infolist()) > 2*1024**3:
            raise ValueError('Workspace snapshot exceeds extraction limit.')
        for item in archive.infolist():
            target=(root/item.filename).resolve()
            if not target.is_relative_to(root) or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Unsafe workspace archive.')
        archive.extractall(root)


def purge(sid):
    api=client()
    # Repeated listing handles pagination without using a stale continuation token.
    while True:
        rows=api.list_objects_v2(Bucket=bucket(),Prefix=prefix(sid)).get('Contents',[])
        if not rows:return
        result=api.delete_objects(Bucket=bucket(),Delete={'Objects':[{'Key':r['Key']} for r in rows]})
        if result.get('Errors'):raise RuntimeError('Private object deletion failed; cleanup will retry.')


def signed_download(key, filename, content_type):
    return client().generate_presigned_url('get_object',Params={'Bucket':bucket(),'Key':key,
        'ResponseContentType':content_type,'ResponseContentDisposition':f'attachment; filename="{filename}"'},ExpiresIn=60)


def preview_response(sess,path):
    """Keep large rendered images outside the Function response size limit."""
    import hashlib
    from fastapi.responses import Response, RedirectResponse
    from . import state
    data=Path(path).read_bytes()
    if len(data)<=4*1024*1024:
        return Response(data,media_type='image/png',headers={'Cache-Control':'no-store'})
    key=prefix(sess.id)+'previews/'+hashlib.sha256(data).hexdigest()+'.png'
    put(key,data,'image/png');state.active(sess)
    url=client().generate_presigned_url('get_object',Params={'Bucket':bucket(),'Key':key,
        'ResponseContentType':'image/png'},ExpiresIn=60)
    return RedirectResponse(url,status_code=302,headers={'Cache-Control':'no-store'})
