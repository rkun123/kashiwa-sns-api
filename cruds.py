import types
from deta import Deta
from fastapi import HTTPException
from schemas import CreatePostPayload, CreateThreadPayload, Post, User, SigninPayload, SignupPayload, Thread
from uuid import uuid4
from more_itertools import ilen
from datetime import datetime
from typing import List, Optional, Dict
from operator import itemgetter
import jwt
import bcrypt
import os

# project key
deta = Deta(os.environ.get('DETA_TOKEN', 'c01jifyn_JnRrTsxwQmg7Uzw8beRTJN7CowUNhKQB'))
test_prefix = os.environ.get('PYTHON_ENV', '')

userDB = deta.Base(f'{test_prefix}users')
threadDB = deta.Base(f'{test_prefix}threads')
postDB = deta.Base(f'{test_prefix}posts')

salt = os.environ.get('PASSWORD_HASH_SALT', '$2a$10$ThXfVCPWwXYx69U8vuxSUu').encode()

def genID():
  return str(uuid4())

def genPasswordHash(password: str):
  hash = bcrypt.hashpw(password.encode(), salt)
  return hash.decode()

def createUser(signupPayload: SignupPayload) -> User:
  id = genID()
  password_hash = genPasswordHash(signupPayload.password)
  user = User(
    email=signupPayload.email,
    name=signupPayload.name,
    description=signupPayload.description,
    password_hash=password_hash,
  )
  users = list(userDB.fetch({ 'email': signupPayload.email }))[0]
  if len(users) >= 1:
    raise HTTPException(status_code=400, detail='Already exists user has same email')

  res = userDB.put(user.dict(), key=id)
  res_user = User(
    key=res['key'],
    email=res['email'],
    name=res['name'],
    description=res['description'],
    created_at=res['created_at'],
    updated_at=res['created_at']
  )
  print(res_user)
  return res_user

def getUserByEmail(email: str) -> User:
  users = list(userDB.fetch({ 'email': email }))[0]
  if len(users) <= 0:
    print('User not found by email')
    raise HTTPException(status_code=401, detail='User not found')
  
  return User(**users[0])

def getUserByKey(key: str) -> User:
  user = userDB.get(key)
  if user == None:
    raise HTTPException(status_code=401, detail='User not found')
  
  return User(**user)

# Threads

def createThread(payload: CreateThreadPayload, user: User) -> Thread:
  threads = list(threadDB.fetch({ 'name': payload.name }))[0]
  if len(threads) >= 1:
    raise HTTPException(status_code=400, detail='Already exists thread has same name')
  
  thread = Thread(
    name = payload.name,
    author_key = user.key
  )
  
  thread_dict = threadDB.put(thread.dict(exclude_none=True))
  return Thread(**thread_dict)

def getThread(key: str) -> Optional[Thread]:
  thread_dict = threadDB.get(key)
  if thread_dict == None:
    return None
  thread = Thread(**thread_dict)
  return thread

def listThread(limit: int = 10, page: int = 1) -> List[Thread]:
  thread_iter = threadDB.fetch(pages=page, buffer=limit)
  thread_dicts = []
  for i in range(page):
    try:
      thread_dicts = next(thread_iter)
    except StopIteration:
      raise HTTPException(status_code=404, detail='specified page is out of range')
  
  def parse_thread(thread_dict: Dict[str, str]) -> Thread:
    t = Thread(**thread_dict)
    user = getUserByKey(t.author_key)
    t.author = user
    return t
  
  threads = list(map(parse_thread, thread_dicts))
  return threads

def createPost(payload: CreatePostPayload, user: User) -> Post:
  post = Post(author_key=user.key, **payload.dict(exclude_none=True))
  post_dict = postDB.put(post.dict(exclude_none=True))
  post = Post(**post_dict)
  return post

def deletePost(post_key: str, user: User):
  post = postDB.get(post_key)
  post = Post(**post)
  post.author = getUserByKey(post.author_key)
  print(post)
  if post.author.key != user.key:
    raise HTTPException(status_code=401, detail='deleting specified post is not permitted')
  
  postDB.delete(post_key) 

def listPosts(thread: Thread, limit: int = 10, page: int = 1) -> List[Post]:
  post_iter = postDB.fetch({ 'thread_key': thread.key })
  all_posts = list(post_iter)[0]
  all_posts = sorted(all_posts, key=itemgetter('created_at'), reverse=True)
  start = limit * (page - 1)
  end = start + limit
  s = slice(start, end)

  if len(all_posts) <= limit * (page - 1):
    raise HTTPException(status_code=404, detail='specified page is out of range')

  post_dicts = all_posts[s]

  def parse_post(post_dict: Dict[str, str]) -> Post:
    p = Post(**post_dict)
    user = getUserByKey(p.author_key)
    p.author = user
    return p
  
  posts = list(map(parse_post, post_dicts))
  return posts