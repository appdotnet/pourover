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


var DEFAULT_FEED_OBJ = {
    max_stories_per_period: 1,
    schedule_period: 1,
    format_mode: 1,
    include_thumb: true,
};

angular.module('pourOver')
.controller('MainCtrl', ['$scope', function ($scope) {

  $scope.schedule_periods = [
    {label: '1 mins', value: 1},
    {label: '5 mins', value: 5},
    {label: '15 mins', value: 15},
    {label: '30 mins', value: 30},
    {label: '60 mins', value: 60},
  ];

  $scope.feed = DEFAULT_FEED_OBJ;

  // initialize and store user data in localStorage

  var client;
  if ($scope.local.accessToken) {
    client = authedAjax($scope.local.accessToken);
  }

  if (!client) {
    return;
  }

  var serialize_feed = function (feed) {
    _.each(['linked_list_mode', 'include_thumb', 'include_summary', 'include_video'], function (el) {
      if (!feed[el]) {
        delete feed[el];
      }
    });

    return feed;
  };
  $scope.feed_error = undefined;
  $scope.$watch('feed', _.debounce(function () {
    var preview_url = 'feed/preview';
    if($scope.feed.feed_id) {
      preview_url = 'feeds/' + $scope.feed.feed_id + '/preview';
    }

    if (!$scope.feed.feed_url) {
      return false;
    }
    jQuery('.loading-icon').show();
    apiRequest({
      url: preview_url,
      data: serialize_feed($scope.feed),
    }, client, window.location + 'api/').always(function () {
        jQuery('.loading-icon').hide();
    }).done(function (resp) {
      $scope.$apply(function (scope) {
        if (resp.status === 'ok') {
          scope.posts = resp.data;
          scope.feed_error = undefined;
        } else {
          scope.posts = undefined;
          scope.feed_error = resp.message;
        }
      });
    });
  }, 300), true);

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

  var updateLoader = Ladda.create(jQuery('[data-save-btn]').get(0));
  $scope.createOrUpdateFeed = function () {
    updateLoader.start();
    var url = 'feeds';
    if ($scope.feed.feed_id)  {
      url = 'feeds/' + $scope.feed.feed_id;
    }
    apiRequest({
      url: url,
      data: serialize_feed($scope.feed),
      method: 'POST',
    }, client, window.location + 'api/').done(function (resp) {
      if (resp.data && resp.data.feed_id) {
        $scope.$apply(function (scope) {
          scope.feed.feed_id = resp.data.feed_id;
        });
      } else {
        window.alert('There was an error saving that feed.');
      }
    }).always(function () {
      updateLoader.stop();
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
        scope.feed = DEFAULT_FEED_OBJ;
        scope.published_entries = [];
        scope.unpublished_entries = [];
      });
    });
  };

  $scope.entryStatus = function (entry) {
    var status = 'Published';

    if (!entry.published) {
      status = 'Unpublished';
    }

    if (entry.overflow_reason) {
      status = entry.overflow_reason;
    }

    return status;
  };

}]);
