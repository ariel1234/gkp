#!/usr/bin/python  
# -*- coding: utf-8 -*-  

from django import forms
from django.conf import settings
from django.forms.models import modelformset_factory, inlineformset_factory
from django.contrib.contenttypes.generic import generic_inlineformset_factory
from django.contrib.auth.decorators import login_required, permission_required
from django.utils.decorators import method_decorator
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate, logout, login
from django.template import RequestContext
from django.views.generic import TemplateView, ListView, DetailView
from django.views.generic.edit import FormView, CreateView, UpdateView, DeleteView
from django.core.urlresolvers import reverse_lazy, resolve, reverse
from django.shortcuts import render, render_to_response
from django.http import HttpResponseRedirect, JsonResponse
from django.utils.encoding import smart_text
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count,Max,Min,Avg

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.vary import vary_on_headers
# protect the view with require_POST decorator
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Q

# map geometry lib
from shapely.geometry import box as Box
from shapely.geometry import Point
from django.template import loader, Context

# django-crispy-forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

# django-filters
from django_filters import FilterSet, BooleanFilter
from django_filters.views import FilterView
import django_filters

# so what
import re,os,os.path,shutil,subprocess, testtools
import random,codecs,unittest,time, tempfile, csv, hashlib
from datetime import datetime as dt
from multiprocessing import Process, Queue
import simplejson as json
import googlemaps
from itertools import groupby
from utility import MyUtility
from crawler import MyCrawler

from pi.models import *

###################################################
#
#	Common utilities
#
###################################################
def class_view_decorator(function_decorator):
	"""Convert a function based decorator into a class based decorator usable
	on class based Views.
	
	Can't subclass the `View` as it breaks inheritance (super in particular),
	so we monkey-patch instead.
	"""
	
	def simple_decorator(View):
		View.dispatch = method_decorator(function_decorator)(View.dispatch)
		return View
	
	return simple_decorator

###################################################
#
#	Static views
#
###################################################
class HomeView (TemplateView):
	template_name = 'pi/common/home_with_login_modal.html'

	def get_context_data(self, **kwargs):
		context = super(TemplateView, self).get_context_data(**kwargs)

		user_auth_form = AuthenticationForm()
		user_registration_form = UserCreationForm()

		context['registration_form']=user_registration_form
		context['auth_form']=user_auth_form
		return context

###################################################
#
#	User views
#
###################################################
class LoginView(FormView):
	template_name = 'registration/login.html'
	success_url = reverse_lazy('school_echart_map_filter')
	form_class = AuthenticationForm
	def form_valid(self,form):
		username = form.cleaned_data['username']
		password = form.cleaned_data['password']
		user = authenticate(username=username, password=password)

		if user is not None and user.is_active:
		    login(self.request, user)
		    return super(LoginView, self).form_valid(form)
		else:
		    return self.form_invalid(form)

class LogoutView(TemplateView):
	template_name = 'registration/logged_out.html'
	def get(self,request):
		logout(request)
    	# Redirect to a success page.
		messages.add_message(request, messages.INFO, 'Thank you for using our service. Hope to see you soon!')
		return HttpResponseRedirect (reverse_lazy('home'))

class UserRegisterView(FormView):
	template_name = 'registration/register_form.html'
	form_class = UserCreationForm
	success_url = reverse_lazy('login')
	def form_valid(self,form):
		user_name = form.cleaned_data['username']
		password = form.cleaned_data['password2']
		if len(User.objects.filter(username = user_name))>0:
			return self.form_invalid(form)
		else:
			user = User.objects.create_user(user_name, '', password)			
			user.save()
			return super(UserRegisterView,self).form_valid(form)

class UserPropertyView(TemplateView):
	template_name=''
	def post(self,request):
		province = request.POST['province']
		student_type = request.POST['student_type']
		score = request.POST['score']

		# get user property obj
		user_profile,created = MyUserProfile.objects.get_or_create(owner=request.user)

		if not province.strip(): user_profile.province=None
		else:
			p = MyAddress.objects.filter(province = province.strip())
			if len(p) == 1: user_profile.province = p[0]

		if student_type: user_profile.student_type = student_type
		if score: user_profile.estimated_score = int(score)

		user_profile.save()

		# refresh current page, whatever it is.
		return HttpResponseRedirect(request.META['HTTP_REFERER'])

###################################################
#
#	Data import views
#
###################################################
class ImportGeneralUploadForm (forms.Form):
	myfile = forms.FileField(
			label = u'选择文件',
			help_text = u''	
		)

@login_required
def import_admission_by_school (request):
	# if this is a POST request we need to process the form data
	if request.method == 'POST':
		# create a form instance and populate it with data from the request:
		form = ImportGeneralUploadForm(request.POST, request.FILES)
		# check whether it's valid:
		if form.is_valid():
			content = request.FILES['myfile'].read().split('\n')
			MyCrawler().admission_by_school_persist([[a.decode('UTF-8') for a in c.split('\t')] for c in content])
			return HttpResponseRedirect(reverse_lazy('admission_school_list'))
						
	# if a GET (or any other method) we'll create a blank form
	else: 
		form = ImportGeneralUploadForm()
		content = ''
		return render(request, 'pi/import/upload.html', {'form': form})

@login_required
def import_admission_by_major (request):
	# if this is a POST request we need to process the form data
	if request.method == 'POST':
		# create a form instance and populate it with data from the request:
		form = ImportGeneralUploadForm(request.POST, request.FILES)
		# check whether it's valid:
		if form.is_valid():
			content = request.FILES['myfile'].read().split('\n')
			MyCrawler().admission_by_major_persist([[a.decode('UTF-8') for a in c.split('\t')] for c in content])
			return HttpResponseRedirect(reverse_lazy('admission_major_list'))
						
	# if a GET (or any other method) we'll create a blank form
	else: 
		form = ImportGeneralUploadForm()
		content = ''
		return render(request, 'pi/import/upload.html', {'form': form})			

###################################################
#
#	MyAdmissionBySchool views
#
###################################################
class MyAdmissionBySchoolListFilter (FilterSet):
	class Meta:
		model = MyAdmissionBySchool
		fields = {'school__name':['contains'],
				'province':['exact'],
				'category':['contains'],
				}

@class_view_decorator(login_required)
class MyAdmissionBySchoolList (FilterView):
	template_name = 'pi/admission/school_list.html'
	paginate_by = 10
	
	def get_filterset_class(self):
		return MyAdmissionBySchoolListFilter	

@class_view_decorator(login_required)
class MyAdmissionBySchoolAdd (CreateView):
	model = MyAdmissionBySchool
	template_name = 'pi/common/add_form.html'
	success_url = reverse_lazy('admission_school_list')
	
	def form_valid(self, form):
		form.instance.created_by = self.request.user
		return super(MyAdmissionBySchoolAdd, self).form_valid(form)

	def get_context_data(self, **kwargs):
		context = super(MyAdmissionBySchoolAdd, self).get_context_data(**kwargs)
		context['title'] = u'新建fenshuxian(admission)'
		context['list_url'] = reverse_lazy('admission_school_list')
		return context

@class_view_decorator(login_required)
class MyAdmissionBySchoolEdit (UpdateView):
	model = MyAdmissionBySchool
	template_name = 'pi/common/edit_form.html'
	
	def get_success_url(self):
		return reverse_lazy('admission_detail', kwargs={'pk':self.get_object().id})
			
	def get_context_data(self, **kwargs):
		context = super(MyAdmissionBySchoolEdit, self).get_context_data(**kwargs)
		context['title'] = u'编辑fenshuxian(admission)'
		context['list_url'] = reverse_lazy('admission_school_list')
		return context

@class_view_decorator(login_required)
class MyAdmissionBySchoolDelete (DeleteView):
	model = MyAdmissionBySchool
	template_name = 'pi/common/delete_form.html'
	success_url = reverse_lazy('admission_school_list')

	def get_context_data(self, **kwargs):
		context = super(MyAdmissionBySchoolDelete, self).get_context_data(**kwargs)
		context['title'] = u'删除fenshuxian(admission)'
		context['list_url'] = reverse_lazy('admission_school_list')
		return context

def admission_school_crawler_view (request):
	base_url = 'http://www.gaokaopai.com/fenshuxian'
	crawler = MyCrawler()
	crawler.thread_fenshu_crawler(base_url, 'school')

	return HttpResponseRedirect(reverse_lazy('admission_school_list'))

###################################################
#
#	MyAdmissionByMajor views
#
###################################################
from django_filters import CharFilter
class MyAdmissionByMajorListFilter (FilterSet):
	major=CharFilter(name='major__name',label="Majors")
	class Meta:
		model = MyAdmissionByMajor
		fields = {'school__name':['contains'],
				'province':['exact'],
				'category':['contains'],
				'year':['exact'],
				'major__name':['contains'],
				}

@class_view_decorator(login_required)
class MyAdmissionByMajorList (FilterView):
	template_name = 'pi/admission/major_list.html'
	paginate_by = 10
	
	def get_filterset_class(self):
		return MyAdmissionByMajorListFilter	

@class_view_decorator(login_required)
class MyAdmissionByMajorAdd (CreateView):
	model = MyAdmissionByMajor
	template_name = 'pi/common/add_form.html'
	success_url = reverse_lazy('admission_major_list')
	
	def form_valid(self, form):
		form.instance.created_by = self.request.user
		return super(MyAdmissionByMajorAdd, self).form_valid(form)

	def get_context_data(self, **kwargs):
		context = super(MyAdmissionByMajorAdd, self).get_context_data(**kwargs)
		context['title'] = u'新建fenshuxian(admission)'
		context['list_url'] = reverse_lazy('admission_major_list')
		return context

@class_view_decorator(login_required)
class MyAdmissionByMajorEdit (UpdateView):
	model = MyAdmissionByMajor
	template_name = 'pi/common/edit_form.html'
	
	def get_success_url(self):
		return reverse_lazy('admission_detail', kwargs={'pk':self.get_object().id})
			
	def get_context_data(self, **kwargs):
		context = super(MyAdmissionByMajorEdit, self).get_context_data(**kwargs)
		context['title'] = u'编辑fenshuxian(admission)'
		context['list_url'] = reverse_lazy('admission_major_list')
		return context

@class_view_decorator(login_required)
class MyAdmissionByMajorDelete (DeleteView):
	model = MyAdmissionByMajor
	template_name = 'pi/common/delete_form.html'
	success_url = reverse_lazy('admission_major_list')

	def get_context_data(self, **kwargs):
		context = super(MyAdmissionByMajorDelete, self).get_context_data(**kwargs)
		context['title'] = u'删除fenshuxian(admission)'
		context['list_url'] = reverse_lazy('admission_major_list')
		return context

def admission_major_crawler_view (request):
	base_url = 'http://www.gaokaopai.com/fenshuxian-sct-2-p'
	crawler = MyCrawler()
	crawler.thread_fenshu_crawler(base_url, 'major')

	return HttpResponseRedirect(reverse_lazy('admission_major_list'))	

###################################################
#
#	MyMajor views
#
###################################################
class MyMajorListFilter (FilterSet):
	class Meta:
		model = MyMajor
		fields = {
				'code':['contains'],		
				'name':['contains'],
				'subcategory':['exact'],
				'degree_type':['contains'],
				'degree':['contains'],
				'course':['contains'],
				}

@class_view_decorator(login_required)
class MyMajorList (FilterView):
	template_name = 'pi/major/list.html'
	paginate_by = 10
	
	def get_filterset_class(self):
		return MyMajorListFilter	

@class_view_decorator(login_required)
class MyMajorAdd (CreateView):
	model = MyMajor
	template_name = 'pi/common/add_form.html'
	success_url = reverse_lazy('major_list')
	
	def form_valid(self, form):
		form.instance.created_by = self.request.user
		return super(MyMajorAdd, self).form_valid(form)

	def get_context_data(self, **kwargs):
		context = super(MyMajorAdd, self).get_context_data(**kwargs)
		context['title'] = u'新建 Major'
		context['list_url'] = reverse_lazy('major_list')
		return context

@class_view_decorator(login_required)
class MyMajorEdit (UpdateView):
	model = MyMajor
	template_name = 'pi/common/edit_form.html'
	
	def get_success_url(self):
		return reverse_lazy('major_detail', kwargs={'pk':self.get_object().id})
			
	def get_context_data(self, **kwargs):
		context = super(MyMajorEdit, self).get_context_data(**kwargs)
		context['title'] = u'编辑 Major'
		context['list_url'] = reverse_lazy('major_list')
		return context

@class_view_decorator(login_required)
class MyMajorDelete (DeleteView):
	model = MyMajor
	template_name = 'pi/common/delete_form.html'
	success_url = reverse_lazy('major_list')

	def get_context_data(self, **kwargs):
		context = super(MyMajorDelete, self).get_context_data(**kwargs)
		context['title'] = u'删除 Major'
		context['list_url'] = reverse_lazy('major_list')
		return context

@class_view_decorator(login_required)
class MyMajorDetail(DetailView):
	model = MyMajor
	template_name = 'pi/major/detail.html'

	def get_context_data(self, **kwargs):
		context = super(MyMajorDetail, self).get_context_data(**kwargs)
		context['list_url'] = reverse_lazy('major_list')
		return context

	def post(self,request,pk):
		# all related schools
		related_schools = self.get_object().schools.all()

		# client request
		draw = int(request.POST['draw'])
		start = int(request.POST['start'])
		length = int(request.POST['length'])
		search_value = request.POST['search[value]']

		for val in search_value.split(','):
			related_schools = related_schools.filter(Q(city__icontains=val) | Q(name__icontains=val))

		result = {
		"draw": draw,
		"recordsTotal": len(related_schools),
		"recordsFiltered": len(related_schools),
		"data":	[[s.city, s.name] for s in related_schools[start:start+length]]
		}
		# return to client
		return HttpResponse(json.dumps(result), content_type='application/javascript')			

def import_major (request):
	code_pat=re.compile('\d+[TK]*')
	degree_pat = re.compile('(?P<name>[^(]+)[(](?P<degree>[^)]+)[)]')

	content = open(os.path.join(settings.MEDIA_ROOT,'major_std_2.csv'), 'r').read().split('\n')
	for (code,name) in filter(lambda x: len(x)==2 and code_pat.search(x[0]) is not None, [c.split(',') for c in content]):
		code = code_pat.search(code.strip()).group()
	
		if degree_pat.search(name):
			degree = degree_pat.search(name).group('degree')
			name = degree_pat.search(name).group('name')			
		else:
			degree = None
		if '应用化学' in name: print 'here', code, name, degree

		if len(code) == 2: # this is category
			cat, created = MyMajorCategory.objects.get_or_create(code=code,name=name)
		elif len(code) == 4: # this is subcategory
			subcat, created = MyMajorSubcategory.objects.get_or_create(code=code,name=name)
			cat,created = MyMajorCategory.objects.get_or_create(code=code[:2])
			subcat.category=cat
			subcat.save()
		else: # this is major
			major,created = MyMajor.objects.get_or_create(name=name.strip())
			major.code = code.strip()
			
			if 'T' in code: major.is_specialized = True
			if 'K' in code: major.is_gov_controlled = True

			subcat, created = MyMajorSubcategory.objects.get_or_create(code=code[:4])
			major.subcategory = subcat
			major.degree = degree
			if int(major.code[:2])>13:
				major.how_long = u'三年'
				major.degree_type = u'专科'
			else:
				major.how_long = u'四年'
				major.degree_type = u'本科'
			major.save()
	return HttpResponseRedirect(reverse_lazy('major_list'))	

def major_crawler_view (request):
	crawler = MyCrawler()
	crawler.thread_major_crawler()
	return HttpResponseRedirect(reverse_lazy('major_list'))	

###################################################
#
#	MySchool views
#
###################################################

class MySchoolListFilter (FilterSet):
	class Meta:
		model = MySchool
		fields = {
				'name':['contains'],		
				'en_name':['contains'],
				}

@class_view_decorator(login_required)
class MySchoolList (FilterView):
	template_name = 'pi/school/list.html'
	paginate_by = 10
	
	def get_filterset_class(self):
		return MySchoolListFilter

@class_view_decorator(login_required)
class MySchoolAdd (CreateView):
	model = MySchool
	template_name = 'pi/common/add_form.html'
	success_url = reverse_lazy('school_list')
	
	def form_valid(self, form):
		form.instance.created_by = self.request.user
		return super(MyMajorAdd, self).form_valid(form)

	def get_context_data(self, **kwargs):
		context = super(MyMajorAdd, self).get_context_data(**kwargs)
		context['title'] = u'新建 School'
		context['list_url'] = reverse_lazy('school_list')
		return context

@class_view_decorator(login_required)
class MySchoolEdit (UpdateView):
	model = MySchool
	template_name = 'pi/common/edit_form.html'
	
	def get_success_url(self):
		return reverse_lazy('school_detail', kwargs={'pk':self.get_object().id})
			
	def get_context_data(self, **kwargs):
		context = super(MySchoolEdit, self).get_context_data(**kwargs)
		context['title'] = u'编辑 School'
		context['list_url'] = reverse_lazy('school_list')
		return context

@class_view_decorator(login_required)
class MySchoolDelete (DeleteView):
	model = MySchool
	template_name = 'pi/common/delete_form.html'
	success_url = reverse_lazy('school_list')

	def get_context_data(self, **kwargs):
		context = super(MySchoolDelete, self).get_context_data(**kwargs)
		context['title'] = u'删除 School'
		context['list_url'] = reverse_lazy('school_list')
		return context

@class_view_decorator(login_required)
class MySchoolDetail(DetailView):
	model = MySchool
	template_name = 'pi/school/detail.html'

	def get_context_data(self, **kwargs):
		context = super(MySchoolDetail, self).get_context_data(**kwargs)
		context['list_url'] = reverse_lazy('school_list')

		# school admission data by year
		school_admission = MyAdmissionBySchool.objects.filte_by_user_profile(self.request.user).filter(school = self.get_object())
		
		school_admission_by_year = {}		
		for year,admission_by_year_list in groupby(school_admission,lambda x:x.year):
			school_admission_by_year[year]=sorted(list(admission_by_year_list),lambda x,y:cmp(x.category,y.category))
		context['school_admission_by_year']=school_admission_by_year

		# school majors
		context['majors'] = self.get_object().mymajor_set.all()

		# related list
		related_schools = MyAdmissionBySchool.objects.filte_by_user_profile(self.request.user).values('batch','school')
		context['related_schools']=related_schools

		return context

@class_view_decorator(login_required)
class MySchoolMapDetail(TemplateView):
	'''
		AJAX post view
	'''
	template_name = 'pi/school/gmap_detail.html'

	def post(self,request):
		obj_id = request.POST['obj_id']
		school = MySchool.objects.get(id=int(obj_id))
		content = loader.get_template(self.template_name)
		html= content.render(Context({'obj':school}))

		return HttpResponse(json.dumps({'html':html}), 
			content_type='application/javascript')	

@class_view_decorator(login_required)
class MySchoolEchartMapFilter(TemplateView):
	template_name = 'pi/school/emap.html'
	def get_context_data(self, **kwargs):
		context = super(TemplateView, self).get_context_data(**kwargs)

		# echart data, group by province
		result = {}
		for s in MySchool.objects.has_province():
			result.setdefault(s.province, []).append(s.id)
		echart_data = [(key.id, key,len(value)) for key,value in result.iteritems()]
		context['echart_data'] = echart_data
		context['echart_data_min'] = min([a[2] for a in echart_data])
		context['echart_data_max'] = max([a[2] for a in echart_data])

		# this url will be AJAX post to get a detail analysis HTML added to this page
		context['analysis_url'] = reverse_lazy('analysis_school_summary_ajax')
		return context

def school_crawler_view (request):
	base_url = 'http://www.gaokaopai.com/daxue-jianjie'
	crawler = MyCrawler()
	crawler.thread_school_crawler(base_url)

	return HttpResponseRedirect(reverse_lazy('school_list'))	

###################################################
#
#	Googlemap views
#
###################################################
class MySchoolMapInfo (TemplateView):
	info_template_name = 'pi/school/gmap_info.html'
	def post(self,request):
		school = MySchool.objects.get(id=int(request.POST['obj_id']))
		info_win_template = loader.get_template(self.info_template_name)
		# infowin Context for html rendering
		c = Context({
			'user': request.user,
			'ip_address': request.META['REMOTE_ADDR'],
			'obj': school
		})
		# return to client
		return HttpResponse(json.dumps({ 
				'info_win_html': info_win_template.render(c)
			}), content_type='application/javascript')			

class MySchoolMapFilter (TemplateView):
	template_name = 'pi/school/gmap.html'
	visible_template_name = 'pi/school/gmap_visible_list.html'

	def get_context_data(self, **kwargs):
		context = super(TemplateView, self).get_context_data(**kwargs)

		# TODO: center is now WuHan. Should be based on User's location
		context['center'] = {'lat':30.593099,'lng':114.305393}
		context['marker_url']=reverse('school_map_filter')
		context['detail_url']=reverse('school_map_detail')
		context['info_win_url']=reverse('school_map_info')
		return context

	def post(self, request):
		coords=request.POST # viewport bounds
		
		# based on filter criteria we conclude a list
		filtered_objs = MySchool.objects.visible((float(coords['sw.k']),float(coords['sw.D']), float(coords['ne.k']),float(coords['ne.D'])))

		markers = []
		visible_template = loader.get_template(self.visible_template_name)

		for s in filtered_objs:
			# Compose data array for client
			markers.append({
					'lat': s.lat,
					'lng': s.lng,	

					# custom data					
					'hash': s.hash,
					'obj_id':s.id,
					'name':s.name,
					'edit': reverse('school_edit',args = [s.id]),
				})

		# Write list html
		# sort is important for using template groupby function
		visible_html = visible_template.render(Context({'objs':filtered_objs, 'total':len(filtered_objs)}))
		
		# return to client
		return HttpResponse(json.dumps({
				'markers':markers, 
				'marker_list_html':visible_html,
				}), content_type='application/javascript')

###################################################
#
#	Analysis views
#
###################################################
class CategorizeSchoolHelper:
	'''
		This is a helper class.
	'''
	def __init__(self):
		pass

	def condition_filter(self,post_data):
		'''
			Based on request.POST to compose a filter that can be used by self.get_objects
			param: request.POST, JSON data
		'''
		filters = {key:post_data[key] for key in post_data}

		# reverse json loads
		try:
			filters['cats']=json.loads(filters['cats'])
		except: filters['cats']=None
		return filters

	def get_objects(self,custom_filters):
		# set up filters
		province = custom_filters.get('province')
		city = custom_filters.get('city')
		school_type = custom_filters.get('school_type')
		batch = custom_filters.get('batch')
		
		# filter by province
		if province: schools = MySchool.objects.filter(province = int(province))
		else: schools = MySchool.objects.all()

		# filter by city
		if city: schools = schools.filter(city=city)

		# filter by school_type
		if school_type: schools=schools.filter(school_type = school_type)

		return schools

	def categorize_schools(self,schools):
		'''
			Group schools into aggregated groups for analysis.
			param: schools
		'''
		bachelors = [s for s in schools if s.has_bachelor_admission]
		associates = [s for s in schools if s.has_associate_admission]
		bachelor_and_associate = list(set(bachelors).intersection(associates))
		pre = [s for s in schools if s.has_pre_admission]

		return {
				u'本科':bachelors,
				u'专科':associates,
				u'既有本科也有专科':bachelor_and_associate,
				u'提前招生':pre			
			}


class AnalysisSchoolSummaryAJAX(TemplateView):
	summary_template_name = 'pi/analysis/schools_by_province_summary.html'

	def post(self,request):
		filters = CategorizeSchoolHelper().condition_filter(request.POST)
		schools = CategorizeSchoolHelper().get_objects(filters)
		categories = CategorizeSchoolHelper().categorize_schools(schools)

		# available vs. active
		available_cats = categories.keys()		
		active_cats = filters['cats'] or available_cats

		# render summary html
		summary = loader.get_template(self.summary_template_name)
		my_context = Context({
			'p_id':filters['province'],
			'schools':schools,
			'categories': categories,
			'available_cats':available_cats,
			'active_cats':active_cats
			})
		html= summary.render(my_context)
		return HttpResponse(json.dumps({'html':html}), 
			content_type='application/javascript')	

class AnalysisSchoolDetailAJAX(TemplateView):
	detail_template_name = 'pi/analysis/schools_detail.html'
	def post(self,request):
		filters = CategorizeSchoolHelper().condition_filter(request.POST)
		schools = CategorizeSchoolHelper().get_objects(filters)
		categories = CategorizeSchoolHelper().categorize_schools(schools)

		# details per section
		detail = loader.get_template(self.detail_template_name)
		html=''
		for cat in filters['cats']:
			objs = categories[cat.strip()]
			max_score = MyAdmissionBySchool.objects.filter(school__in=objs).aggregate(Max('max_score'))['max_score__max']
			min_score = MyAdmissionBySchool.objects.filter(school__in=objs).aggregate(Min('min_score'))['min_score__min']
			max_score = MyAdmissionBySchool.objects.filter(school__in=objs).filter(max_score = max_score)[0]
			min_score = MyAdmissionBySchool.objects.filter(school__in=objs).filter(min_score = min_score)[0]
			my_context=Context({
				'subject':cat.strip(),
				'objs':objs,
				'max_score':max_score,
				'min_score':min_score,
				})

			my_context['by_batch']=(
				(u'一批',len([o for o in objs if o.is_1st_batch])),
				(u'二批',len([o for o in objs if o.is_2nd_batch])),
				(u'三批',len([o for o in objs if o.is_3rd_batch]))
			)

			html+= detail.render(my_context)
		return HttpResponse(json.dumps({'html':html}), 
			content_type='application/javascript')	


class AnalysisSchoolByProvince(TemplateView):		
	template_name = 'pi/analysis/schools_by_province.html'
	def get_context_data(self, **kwargs):
		context = super(TemplateView, self).get_context_data(**kwargs)
		context['province'] = MyAddress.objects.get(id=int(kwargs['pk']))
		context['schools'] = MySchool.objects.filter(province=int(kwargs['pk']))
		return context