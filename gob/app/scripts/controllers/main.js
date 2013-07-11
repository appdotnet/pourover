'use strict';


var authedAjax = function (accessToken) {
  return function (conf) {
    conf.headers = conf.headers || {};
    conf.headers.Authorization = 'Bearer ' + accessToken;

    return jQuery.ajax(conf);
  };
};

var apiRequest = function (conf, client, base) {
  base = base || 'https://alpha-api.app.net/stream/0';
  conf.url = base + conf.url;
  return client(conf);
};

var getUserData = function (client) {
  return apiRequest({
    url: '/users/me',
  }, client);
};


angular.module('frontendApp')
.controller('MainCtrl', ['$scope', function ($scope) {

  $scope.schedule_periods = [
    {label: '1 mins', value: 1},
    {label: '5 mins', value: 5},
    {label: '15 mins', value: 15},
    {label: '30 mins', value: 30},
    {label: '60 mins', value: 60},
  ];

  $scope.feed = {
    max_stories_per_period: 1,
    schedule_period: 1
  };

  // initialize and store user data in localStorage
  $scope.local = JSON.parse(localStorage.data || '{}');
  $scope.$watch('local', function () {
    localStorage.data = JSON.stringify($scope.local);
  }, true);

  $scope.authenticated = false;
  $scope.$watch('local.accessToken', function () {
    $scope.authenticated = ($scope.local.accessToken) ? true : false;
  });

  $scope.logout = function () {
    localStorage.data = '{}';
    window.location = window.location;
    return false;
  };

  $scope.local.accessToken = $scope.local.accessToken || jQuery.url(window.location).fparam('access_token');
  var client;
  if ($scope.local.accessToken) {
    client = authedAjax($scope.local.accessToken);
  }

  if (window.location.hash) {
    window.history.replaceState({}, window.title, '/');
    window.location = window.location;
  }

  if (!client) {
    return;
  }

  $scope.$watch('feed', function () {
    apiRequest({
      url:'feed/preview',
      data: $scope.feed,
    }, client, window.location + 'api/').done(function (resp) {
      $scope.$apply(function (scope) {
        scope.posts = resp.data;
      });
    });
  }, true);

  apiRequest({
    url: 'feeds',
    method: 'GET',
  }, client, window.location + 'api/').done(function (resp) {
    if (resp.data && resp.data.length) {
      $scope.$apply(function (scope) {
        scope.feed = resp.data[0];
      });
    }
  });

  getUserData(client).done(function (resp) {
    $scope.$apply(function (scope) {
      scope.current_user = resp.data;
    });
  });

  var refreshEntries = function () {
    apiRequest({
      url: 'feeds/' + $scope.feed.feed_id + '/published',
      method: 'GET',
    }, client, window.location + 'api/').done(function (resp) {
      if (resp.data && resp.data.entries) {
        $scope.$apply(function (scope) {
          scope.published_entries = resp.data.entries;
        });
      }
    });

    apiRequest({
      url: 'feeds/' + $scope.feed.feed_id + '/unpublished',
      method: 'GET',
    }, client, window.location + 'api/').done(function (resp) {
      if (resp.data && resp.data.entries) {
        $scope.$apply(function (scope) {
          scope.unpublished_entries = resp.data.entries;
        });
      }
    });
  };

  $scope.publishEntry = function (entry) {
    apiRequest({
      url: 'feeds/' + $scope.feed.feed_id + '/entries/' + entry.id + '/publish',
      method: 'POST',
    }, client, window.location + 'api/').done(function () {
      refreshEntries();
    });
  };

  $scope.$watch('feed.feed_id', function () {
    if (!$scope.feed.feed_id) {
      return;
    }
    refreshEntries();
  });

  $scope.createOrUpdateFeed = function () {
    var url = 'feeds';
    if ($scope.feed.feed_id)  {
      url = 'feeds/' + $scope.feed.feed_id;
    }
    apiRequest({
      url: url,
      data: $scope.feed,
      method: 'POST',
    }, client, window.location + 'api/').done(function (resp) {
      $scope.$apply(function (scope) {
        scope.feed.feed_id = resp.data.feed_id;
      });
    });

    return false;
  };

  $scope.deleteFeed = function () {
    var sure = window.confirm('Are you sure you want to delete this feed?');
    if (!sure) {
      return;
    }

    apiRequest({
      url: 'feeds/' + $scope.feed.feed_id,
      method: 'DELETE',
    }, client, window.location + 'api/').done(function () {
      $scope.$apply(function (scope) {
        scope.feed = {
          max_stories_per_period: 1,
          schedule_period: 1
        };
        scope.published_entries = undefined;
        scope.unpublished_entries = undefined;
      });
    });
  };

  $scope.entryStatus = function (entry) {
    var status = 'Published';

    if (!entry.published) {
      status = 'unpublished';
    }

    if (entry.overflow_reason) {
      status = entry.overflow_reason;
    }

    return status;
  };

}]);
