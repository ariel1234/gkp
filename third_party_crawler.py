#!/usr/bin/python  
# -*- coding: utf-8 -*- 
import sys,time,os,gc,csv
import lxml.html
import urllib, urllib2
import simplejson as json
import pytz
import socks
import socket
import logging
from stem import Signal
from stem.control import Controller
from random import randint
import time

# setup Django
import django
sys.path.append(os.path.join(os.path.dirname(__file__), 'gaokao'))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gaokao.settings")
from django.conf import settings
from django.utils import timezone
from django.core.files import File

# import models
from pi.models import *
from pi.crawler import MyBaiduCrawler

class TorUtility():
	def __init__(self):
		user_agent = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.0.7) Gecko/2009021910 Firefox/3.0.7'
		self.headers={'User-Agent':user_agent}
		self.ip_url = 'http://icanhazip.com/'
		self.logger = logging.getLogger('gkp')

	def renewTorIdentity(self,passAuth):
	    try:
	        s = socket.socket()
	        s.connect(('localhost', 9051))
	        s.send('AUTHENTICATE "{0}"\r\n'.format(passAuth))
	        resp = s.recv(1024)

	        if resp.startswith('250'):
	            s.send("signal NEWNYM\r\n")
	            resp = s.recv(1024)

	            if resp.startswith('250'):
	                self.logger.info("Identity renewed")
	            else:
	                self.logger.info("response 2:%s"%resp)

	        else:
	            self.logger.info("response 1:%s"%resp)

	    except Exception as e:
	        self.logger.error("Can't renew identity: %s"%e)

	def renew_connection(self):
		with Controller.from_port(port = 9051) as controller:
	  		controller.authenticate('natalie')
	  		controller.signal(Signal.NEWNYM)

		self.logge.info('*'*50)
		self.logger.info('\t'*6+'Renew TOR IP: %s'%self.request(self.ip_url))
		self.logger.info('*'*50)
	
	def _set_urlproxy(self):
	    proxy_support = urllib2.ProxyHandler({"http" : "127.0.0.1:8118"})
	    opener = urllib2.build_opener(proxy_support)
	    urllib2.install_opener(opener)

	def request(self, url, retry=3):
		go = 0
		while go < retry:
			try:
				self._set_urlproxy()
				request=urllib2.Request(url, None, self.headers)
				return urllib2.urlopen(request).read()
			except:
				self.logger.error('Retrying #%d' % go)
				go += 1
				self.renew_connection()

	def current_ip(self):
		return self.request(self.ip_url)

class MyBaiduCrawler():
	def __init__(self,tor):
		self.tor_util = tor
		self.logger = logging.getLogger('gkp')

	def tieba(self,keyword):
		baidu_url = 'http://tieba.baidu.com/f?kw=%s&ie=utf-8'%urllib.quote(keyword.encode('utf-8'))		
		content = self.tor_util.request(baidu_url)
		html = lxml.html.document_fromstring(content)

		threads = []
		for t in html.xpath('//li[contains(@class, "j_thread_list")]'):
			stats = json.loads(t.get('data-field'))
			if stats['is_top'] or not stats['reply_num']: continue  # sticky posts, always on top, so we skip these

			# basic thread infos
			this_thread = {
				'source':'百度贴吧',
				'author': stats['author_name'],
				'author_id':stats['id'],
				'url':'http://tieba.baidu.com/p/%d' % stats['id'],
				'reply_num': stats['reply_num'],
				'title': t.xpath('.//a[contains(@class,"j_th_tit")]')[0].text_content().strip(), # post title line
				'abstract': t.xpath('.//div[contains(@class,"threadlist_abs_onlyline")]')[0].text_content().strip(), # post abstracts
				'last_timestamp': t.xpath('.//span[contains(@class,"threadlist_reply_date")]')[0].text_content().strip()
			}

			imgs = []
			for i in t.xpath('.//img[contains(@class,"threadlist_pic")]'):
				#imgs.append(i.get('original')) # this is thumbnail
				imgs.append(i.get('bpic')) # this is full size pic, has to save locally first. Link to Baidu won't work.
			this_thread['imgs']=imgs

			# add to list
			threads.append(this_thread)

		return threads

	def consumer(self, params):
		self.logger.info(params)

		school = MySchool.objects.get(name=params['keyword'])
		results = self.tieba(params['keyword'])
		self.logger.info(len(results))

		for t in results:
			# make django's timezone-aware timestamp
			if ':' in t['last_timestamp']:
				tmp = t['last_timestamp'].split(':')
				now = timezone.now()
				post_timestamp = dt(now.year,now.month,now.day,int(tmp[0]),int(tmp[1]))
				post_timestamp = pytz.timezone(timezone.get_default_timezone_name()).localize(post_timestamp)
			else: post_timestamp = None

			# create records in DB
			data,created = MyBaiduStream.objects.get_or_create(
				school = school,
				author = t['author'],
				url_original = t['url'],
				reply_num = t['reply_num'],
				name = t['title'][:64],
				description = t['abstract'],
			)
			if post_timestamp: 
				data.last_updated=post_timestamp
				data.save()

			# look up its attachments, if any
			for img_url in t['imgs']:
				if len(Attachment.objects.filter(source_url=img_url)): continue # exist

				self.logger.info('retrieving images [%s]' % img_url)
				img_data = urllib.urlretrieve(img_url)
				attchment = Attachment(
					source_url = img_url,
					content_object=data,
					file=File(open(img_data[0]))
				).save()

from threading import Thread
class MyRequestConsumer(Thread):
	def __init__(self):
		Thread.__init__(self)
		self.logger = logging.getLogger('gkp')
		self.tor = TorUtility()

	def run(self):
		for i in range(5):
			self.logger.info('\t'*6+'Renew TOR IP: %s'%self.tor.current_ip())

			self.logger.info('Queue size %d'%MyCrawlerRequest.objects.count())

			reqs = MyCrawlerRequest.objects.all().order_by('-created').values('source','params')[:10]
			targets = list(set([(t['source'],t['params']) for t in reqs]))
			
			self.logger.info('Downsized to %d'%len(targets))

			for req in targets:
				if req[0] == 1: # baidu tieba
					MyBaiduCrawler(self.tor).consumer(json.loads(req[1]))

				# clear queue for all other requests since data have been updated
				for m in MyCrawlerRequest.objects.filter(source=req[0],params=req[1]):
					m.delete()

			# Sleep for random time between 1 ~ 3 second
			secondsToSleep = randint(1, 5)
			print('%s sleeping fo %d seconds...' % (self.getName(), secondsToSleep))
			time.sleep(secondsToSleep)
 
def main():
	django.setup()

	# create logger with 'spam_application'
	logger = logging.getLogger('gkp')
	logger.setLevel(logging.DEBUG)
	# create file handler which logs even debug messages
	fh = logging.FileHandler('gkp.log')
	fh.setLevel(logging.DEBUG)
	# create console handler with a higher log level
	ch = logging.StreamHandler()
	ch.setLevel(logging.ERROR)
	# create formatter and add it to the handlers
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	fh.setFormatter(formatter)
	ch.setFormatter(formatter)
	# add the handlers to the logger
	logger.addHandler(fh)
	logger.addHandler(ch)

	con_1 = MyRequestConsumer()
	con_1.setName('Consumer 1')

	print 'Starting.... thread'
	con_1.start()
	
if __name__=='__main__':
	main()