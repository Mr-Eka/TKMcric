import qrcode
import io
import base64

from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import models
from .models import Team, Player, Match, Innings, Ball
from .forms import TeamForm, PlayerForm, MatchForm, InningsForm, BallForm, TossForm


def home(request):
    total_teams = Team.objects.count()
    total_matches = Match.objects.count()
    live_matches = Match.objects.filter(status='live')
    upcoming_matches = Match.objects.filter(status='upcoming').order_by('match_date')[:5]

    context = {
        'total_teams': total_teams,
        'total_matches': total_matches,
        'live_matches': live_matches,
        'upcoming_matches': upcoming_matches,
    }
    return render(request, 'teams/home.html', context)

# ---------- PUBLIC VIEWS ----------

def team_list(request):
    search_query = request.GET.get('q', '')
    teams = Team.objects.all()

    if search_query:
        teams = teams.filter(name__icontains=search_query) | teams.filter(short_name__icontains=search_query)

    return render(request, 'teams/team_list.html', {'teams': teams, 'search_query': search_query})


def team_detail(request, pk):
    team = get_object_or_404(Team, pk=pk)
    players = team.players.all()
    is_owner = request.user.is_authenticated and team.created_by_id == request.user.id
    return render(request, 'teams/team_detail.html', {'team': team, 'players': players, 'is_owner': is_owner})


def player_career(request, pk):
    player = get_object_or_404(Player, pk=pk)

    balls_faced = Ball.objects.filter(batsman=player)
    balls_bowled = Ball.objects.filter(bowler=player)

    total_runs = sum(b.runs for b in balls_faced)
    total_balls_faced = balls_faced.exclude(extra_type='wide').count()
    total_fours = balls_faced.filter(runs=4).count()
    total_sixes = balls_faced.filter(runs=6).count()
    times_out = balls_faced.filter(is_wicket=True, player_out=player).count()
    innings_batted = balls_faced.values('innings').distinct().count()

    career_strike_rate = round((total_runs / total_balls_faced) * 100, 1) if total_balls_faced else 0.0
    career_average = round(total_runs / times_out, 1) if times_out else total_runs

    total_balls_bowled = balls_bowled.filter(extra_type__in=['', 'bye', 'legbye']).count()
    total_runs_conceded = sum(b.total_runs() for b in balls_bowled.exclude(extra_type__in=['bye', 'legbye']))
    total_wickets = balls_bowled.filter(is_wicket=True).exclude(wicket_type='runout').count()
    innings_bowled = balls_bowled.values('innings').distinct().count()

    overs_bowled_display = f"{total_balls_bowled // 6}.{total_balls_bowled % 6}"
    career_economy = round(total_runs_conceded / (total_balls_bowled / 6), 2) if total_balls_bowled else 0.0

    context = {
        'player': player,
        'innings_batted': innings_batted,
        'total_runs': total_runs,
        'total_balls_faced': total_balls_faced,
        'total_fours': total_fours,
        'total_sixes': total_sixes,
        'times_out': times_out,
        'career_strike_rate': career_strike_rate,
        'career_average': career_average,
        'innings_bowled': innings_bowled,
        'overs_bowled_display': overs_bowled_display,
        'total_runs_conceded': total_runs_conceded,
        'total_wickets': total_wickets,
        'career_economy': career_economy,
    }
    return render(request, 'teams/player_career.html', context)


def match_list(request):
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')

    matches = Match.objects.all().order_by('-match_date')

    if search_query:
        matches = matches.filter(team_a__name__icontains=search_query) | matches.filter(team_b__name__icontains=search_query) | matches.filter(team_a__short_name__icontains=search_query) | matches.filter(team_b__short_name__icontains=search_query)

    if status_filter:
        matches = matches.filter(status=status_filter)

    context = {
        'matches': matches.distinct(),
        'search_query': search_query,
        'status_filter': status_filter,
        'status_choices': Match.STATUS_CHOICES,
    }
    return render(request, 'teams/match_list.html', context)


def match_history(request):
    completed_matches = Match.objects.filter(status='completed').order_by('-match_date')
    return render(request, 'teams/match_history.html', {'matches': completed_matches})


def standings(request):
    teams = Team.objects.all()
    table = []

    for team in teams:
        matches_played = Match.objects.filter(status='completed').filter(
            models.Q(team_a=team) | models.Q(team_b=team)
        )

        played = matches_played.count()
        won = matches_played.filter(winner=team).count()
        lost = matches_played.exclude(winner=team).exclude(winner__isnull=True).count()
        tied = matches_played.filter(winner__isnull=True).count()
        points = (won * 2) + (tied * 1)

        total_runs_scored = 0
        total_overs_faced = 0
        total_runs_conceded = 0
        total_overs_bowled = 0

        for match in matches_played:
            for innings in match.innings.all():
                legal_balls = innings.legal_balls_count()
                overs = legal_balls / 6
                if innings.batting_team == team:
                    total_runs_scored += innings.total_runs()
                    total_overs_faced += overs
                else:
                    total_runs_conceded += innings.total_runs()
                    total_overs_bowled += overs

        run_rate_for = (total_runs_scored / total_overs_faced) if total_overs_faced else 0
        run_rate_against = (total_runs_conceded / total_overs_bowled) if total_overs_bowled else 0
        nrr = round(run_rate_for - run_rate_against, 3)

        table.append({
            'team': team,
            'played': played,
            'won': won,
            'lost': lost,
            'tied': tied,
            'points': points,
            'nrr': nrr,
        })

    table.sort(key=lambda x: (-x['points'], -x['nrr']))

    return render(request, 'teams/standings.html', {'table': table})


def player_leaderboard(request):
    players = Player.objects.all()
    leaderboard = []

    for player in players:
        balls_faced = Ball.objects.filter(batsman=player)
        balls_bowled = Ball.objects.filter(bowler=player)

        total_runs = sum(b.runs for b in balls_faced)
        total_wickets = balls_bowled.filter(is_wicket=True).exclude(wicket_type='runout').count()
        total_fours = balls_faced.filter(runs=4).count()
        total_sixes = balls_faced.filter(runs=6).count()

        points = total_runs + (total_fours * 1) + (total_sixes * 2) + (total_wickets * 20)

        if total_runs > 0 or total_wickets > 0:
            leaderboard.append({
                'player': player,
                'runs': total_runs,
                'wickets': total_wickets,
                'points': points,
            })

    leaderboard.sort(key=lambda x: -x['points'])

    return render(request, 'teams/leaderboard.html', {'leaderboard': leaderboard[:20]})

def match_detail(request, pk):
    match = get_object_or_404(Match, pk=pk)
    innings_list = match.innings.all()
    is_owner = request.user.is_authenticated and match.created_by_id == request.user.id
    motm = match.calculate_man_of_match() if match.status == 'completed' else None
    return render(request, 'teams/match_detail.html', {'match': match, 'innings_list': innings_list, 'is_owner': is_owner, 'motm': motm})


def live_scoreboard(request, pk):
    match = get_object_or_404(Match, pk=pk)
    innings_list = match.innings.all().order_by('innings_number')
    recent_balls = Ball.objects.filter(innings__match=match).order_by('-timestamp')[:5]

    current_innings = innings_list.last()
    target_info = current_innings.target_info() if current_innings else None

    context = {
        'match': match,
        'current_innings': current_innings,
        'recent_balls': recent_balls,
        'target_info': target_info,
    }
    return render(request, 'teams/live_scoreboard.html', context)

def match_qr_code(request, pk):
    match = get_object_or_404(Match, pk=pk)
    live_url = request.build_absolute_uri(reverse('live_scoreboard', args=[match.pk]))

    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(live_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    context = {
        'match': match,
        'qr_base64': qr_base64,
        'live_url': live_url,
    }
    return render(request, 'teams/match_qr.html', context)

# ---------- PRIVATE / WRITE-ACCESS VIEWS (login required) ----------

@login_required
def team_create(request):
    if request.method == 'POST':
        form = TeamForm(request.POST, request.FILES)
        if form.is_valid():
            team = form.save(commit=False)
            team.created_by = request.user
            team.save()
            return redirect('team_list')
    else:
        form = TeamForm()

    return render(request, 'teams/team_form.html', {'form': form})


@login_required
def player_create(request, team_pk):
    team = get_object_or_404(Team, pk=team_pk)

    if team.created_by_id != request.user.id:
        messages.error(request, "Only the team creator can add players.")
        return redirect('team_detail', pk=team.pk)

    if request.method == 'POST':
        form = PlayerForm(request.POST, request.FILES)
        if form.is_valid():
            player = form.save(commit=False)
            player.team = team
            player.save()
            return redirect('team_detail', pk=team.pk)
    else:
        form = PlayerForm()

    return render(request, 'teams/player_form.html', {'form': form, 'team': team})


@login_required
def player_edit(request, pk):
    player = get_object_or_404(Player, pk=pk)

    if player.team.created_by_id != request.user.id:
        messages.error(request, "Only the team creator can edit players.")
        return redirect('team_detail', pk=player.team.pk)

    if request.method == 'POST':
        form = PlayerForm(request.POST, request.FILES, instance=player)
        if form.is_valid():
            form.save()
            return redirect('team_detail', pk=player.team.pk)
    else:
        form = PlayerForm(instance=player)

    return render(request, 'teams/player_form.html', {'form': form, 'team': player.team, 'editing': True})
@login_required
def match_create(request):
    if request.method == 'POST':
        form = MatchForm(request.POST)
        if form.is_valid():
            match = form.save(commit=False)
            match.created_by = request.user
            match.save()
            return redirect('match_detail', pk=match.pk)
    else:
        form = MatchForm()

    return render(request, 'teams/match_form.html', {'form': form})


@login_required
def toss_update(request, pk):
    match = get_object_or_404(Match, pk=pk)

    if match.created_by_id != request.user.id:
        messages.error(request, "Only the match creator can set the toss.")
        return redirect('match_detail', pk=match.pk)

    if request.method == 'POST':
        form = TossForm(request.POST, instance=match, match=match)
        if form.is_valid():
            form.save()
            return redirect('match_detail', pk=match.pk)
    else:
        form = TossForm(instance=match, match=match)

    return render(request, 'teams/toss_form.html', {'form': form, 'match': match})


@login_required
def innings_create(request, match_pk):
    match = get_object_or_404(Match, pk=match_pk)

    if match.created_by_id != request.user.id:
        messages.error(request, "Only the match creator can start an innings.")
        return redirect('match_detail', pk=match.pk)

    if request.method == 'POST':
        form = InningsForm(request.POST, match=match)
        if form.is_valid():
            innings = form.save(commit=False)
            innings.match = match
            innings.current_striker = form.cleaned_data['opener_striker']
            innings.current_non_striker = form.cleaned_data['opener_non_striker']
            innings.current_bowler = form.cleaned_data['opening_bowler']
            innings.save()
            match.status = 'live'
            match.save()
            return redirect('scoring', pk=innings.pk)
    else:
        form = InningsForm(match=match)
        form.fields['batting_team'].queryset = Team.objects.filter(pk__in=[match.team_a.pk, match.team_b.pk])
        form.fields['bowling_team'].queryset = Team.objects.filter(pk__in=[match.team_a.pk, match.team_b.pk])

    return render(request, 'teams/inning_form.html', {'form': form, 'match': match})


@login_required
def scoring(request, pk):
    innings = get_object_or_404(Innings, pk=pk)
    match = innings.match

    if match.created_by_id != request.user.id:
        messages.error(request, "Only the match creator can update the score.")
        return redirect('live_scoreboard', pk=match.pk)

    balls = innings.balls.all().order_by('-timestamp')[:10]

    if request.method == 'POST':
        form = BallForm(request.POST, innings=innings)
        if form.is_valid():
            ball = form.save(commit=False)
            ball.innings = innings

            legal_balls_so_far = innings.legal_balls_count()
            ball.over_number = legal_balls_so_far // 6
            ball.ball_number = (legal_balls_so_far % 6) + 1
            ball.save()

            is_legal_ball = ball.extra_type not in ['wide', 'noball']
            runs_this_ball = ball.runs

            if ball.is_wicket:
                next_batsman = form.cleaned_data.get('next_batsman')
                if ball.player_out_id == innings.current_striker_id:
                    innings.current_striker = next_batsman
                elif ball.player_out_id == innings.current_non_striker_id:
                    innings.current_non_striker = next_batsman
            else:
                innings.current_striker = ball.batsman

            if runs_this_ball % 2 == 1:
                innings.current_striker, innings.current_non_striker = innings.current_non_striker, innings.current_striker

            new_legal_count = innings.legal_balls_count()
            if is_legal_ball and new_legal_count % 6 == 0 and new_legal_count > 0:
                innings.current_striker, innings.current_non_striker = innings.current_non_striker, innings.current_striker

            innings.current_bowler = ball.bowler
            innings.save()

            check_match_completion(innings)

            return redirect('scoring', pk=innings.pk)
    else:
        form = BallForm(innings=innings)

    context = {
        'innings': innings,
        'balls': balls,
        'form': form,
        'total_runs': innings.total_runs(),
        'total_wickets': innings.total_wickets(),
        'overs_bowled': innings.overs_bowled(),
        'batting_stats': innings.batting_stats(),
        'bowling_stats': innings.bowling_stats(),
        'partnership': innings.current_partnership(),
        'target_info': innings.target_info(),
    }
    return render(request, 'teams/scoring.html', context)


def check_match_completion(innings):
    match = innings.match
    max_legal_balls = match.overs_limit * 6

    innings_done = (
        innings.legal_balls_count() >= max_legal_balls or
        innings.total_wickets() >= 10
    )

    if innings.innings_number == 2 and not innings_done:
        first_innings = match.innings.filter(innings_number=1).first()
        if first_innings and innings.total_runs() > first_innings.total_runs():
            innings_done = True

    if innings_done:
        innings.is_completed = True
        innings.save()

        first_innings = match.innings.filter(innings_number=1).first()
        second_innings = match.innings.filter(innings_number=2).first()

        if first_innings and second_innings and second_innings.is_completed:
            score1 = first_innings.total_runs()
            score2 = second_innings.total_runs()

            if score2 > score1:
                match.winner = second_innings.batting_team
                margin = 10 - second_innings.total_wickets()
                match.result_summary = f"{second_innings.batting_team.short_name} won by {margin} wicket(s)"
            elif score1 > score2:
                match.winner = first_innings.batting_team
                margin = score1 - score2
                match.result_summary = f"{first_innings.batting_team.short_name} won by {margin} run(s)"
            else:
                match.result_summary = "Match tied"

            match.status = 'completed'
            match.save()