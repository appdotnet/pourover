'use strict';

angular.module('pourOver')
.controller('FeedDetailCtrl', ['$rootScope', '$scope', 'ApiClient', '$routeParams', '$location', 'Feeds', 'User',function ($rootScope, $scope, ApiClient, $routeParams, $location, Feeds, User) {

  $scope.schedule_periods = [
    {label: '1 mins', value: 1},
    {label: '5 mins', value: 5},
    {label: '15 mins', value: 15},
    {label: '30 mins', value: 30},
    {label: '60 mins', value: 60},
  ];

  if ($routeParams.feed_id) {
    if ($routeParams.feed_id !== 'new') {
      Feeds.setFeed($routeParams.feed_id);
    } else {
      Feeds.setNewFeed();
    }
  }

  $scope.feed_error = undefined;
  $scope.$watch('feed', _.debounce(function () {
    var preview_url = 'feed/preview';
    if($rootScope.feed.feed_id) {
      preview_url = 'feeds/' + $rootScope.feed.feed_id + '/preview';
    }

    if (!$rootScope.feed.feed_url) {
      return false;
    }
    jQuery('.loading-icon').show();
    ApiClient.get({
      url: preview_url,
      params: Feeds.serialize_feed($rootScope.feed)
    }).error(function () {
      jQuery('.loading-icon').hide();
    }).success(function (resp, status, headers, config) {
      if (resp.status === 'ok') {
        $scope.posts = resp.data;
        $scope.feed_error = undefined;
      } else {
        $scope.posts = undefined;
        $scope.feed_error = resp.message;
      }
      jQuery('.loading-icon').hide();
    });
  }, 300), true);

  var refreshEntries = function () {
    ApiClient.get({
      url: 'feeds/' + $rootScope.feed.feed_id + '/latest'
    }).success(function (resp) {
      if (resp.data && resp.data.entries) {
        $scope.published_entries = resp.data.entries;
      }
    });

    ApiClient.get({
      url: 'feeds/' + $rootScope.feed.feed_id + '/unpublished'
    }).success(function (resp, status, headers, config) {
      if (resp.data && resp.data.entries) {
        $scope.unpublished_entries = resp.data.entries;
      }
    });
  };

  $scope.publishEntry = function (entry) {
    ApiClient.post({
      url: 'feeds/' + $rootScope.feed.feed_id + '/entries/' + entry.id + '/publish'
    }).success(function () {
      refreshEntries();
    });
  };

  $scope.$watch('feed.feed_id', function () {
    if (!$rootScope.feed.feed_id) {
      return;
    }
    refreshEntries();
  });

  var updateLoader = Ladda.create(jQuery('[data-save-btn]').get(0));
  $scope.createOrUpdateFeed = function () {
    updateLoader.start();
    var method = ($rootScope.feed.feed_id) ? 'updateFeed' : 'createFeed';
    Feeds[method]($rootScope.feed).then(updateLoader.stop, function () {
      updateLoader.stop();
      window.alert('Something wen\'t wrong while saving your feed');
    });

    return false;
  };

  $scope.deleteFeed = function () {
    var sure = window.confirm('Are you sure you want to delete this feed?');
    if (!sure) {
      return false;
    }

    var feed_id = $rootScope.feed.feed_id;
    Feeds.deleteFeed(feed_id).then(function () {
      delete $scope.published_entries;
      delete $scope.unpublished_entries;
      $location.path('/');
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