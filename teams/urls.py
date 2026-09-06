from django.urls import path
from . import views

urlpatterns = [
    path('', views.team_list, name='team_list'),
    path('teams/add/', views.team_create, name='team_create'),
    path('teams/<int:pk>/', views.team_detail, name='team_detail'),
    path('teams/<int:team_pk>/players/add/', views.player_create, name='player_create'),
    path('players/<int:pk>/career/', views.player_career, name='player_career'),

    path('matches/', views.match_list, name='match_list'),
    path('matches/add/', views.match_create, name='match_create'),
    path('matches/history/', views.match_history, name='match_history'),
    path('matches/<int:pk>/', views.match_detail, name='match_detail'),
    path('matches/<int:pk>/toss/', views.toss_update, name='toss_update'),
    path('matches/<int:match_pk>/start-innings/', views.innings_create, name='innings_create'),
    path('matches/<int:pk>/live/', views.live_scoreboard, name='live_scoreboard'),

    path('standings/', views.standings, name='standings'),

    path('scoring/<int:pk>/', views.scoring, name='scoring'),
]