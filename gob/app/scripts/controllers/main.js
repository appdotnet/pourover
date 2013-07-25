'use strict';



var DEFAULT_FEED_OBJ = {
  max_stories_per_period: 1,
  schedule_period: 1,
  format_mode: 1,
  include_thumb: true
};

angular.module('pourOver')
.controller('MainCtrl', ['$scope', 'ApiClient', function ($scope, ApiClient) {

  $scope.schedule_periods = [
    {label: '1 mins', value: 1},
    {label: '5 mins', value: 5},
    {label: '15 mins', value: 15},
    {label: '30 mins', value: 30},
    {label: '60 mins', value: 60},
  ];

  $scope.feed = DEFAULT_FEED_OBJ;
  $scope.feeds = [];

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
    ApiClient.get({
      url: preview_url,
      params: serialize_feed($scope.feed)
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

  ApiClient.get({
    url: 'feeds'
  }).success(function (resp, status, headers, config) {
    if (resp.data && resp.data.length) {
      $scope.feed = resp.data[0];
      $scope.feeds = resp.data;
    }
  });

  ApiClient.get({
    url: 'me'
  }).success(function (resp, status, headers, config) {
    $scope.current_user = resp.data;
  });

  var refreshEntries = function () {
    ApiClient.get({
      url: 'feeds/' + $scope.feed.feed_id + '/published'
    }).success(function (resp) {
      if (resp.data && resp.data.entries) {
        $scope.published_entries = resp.data.entries;
      }
    });

    ApiClient.get({
      url: 'feeds/' + $scope.feed.feed_id + '/unpublished'
    }).success(function (resp, status, headers, config) {
      if (resp.data && resp.data.entries) {
        $scope.unpublished_entries = resp.data.entries;
      }
    });
  };

  $scope.publishEntry = function (entry) {
    ApiClient.post({
      url: 'feeds/' + $scope.feed.feed_id + '/entries/' + entry.id + '/publish'
    }).success(function () {
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
    ApiClient.post({
      url: url,
      data: serialize_feed($scope.feed)
    }).success(function (resp, status, headers, config) {
      if (resp.data && resp.data.feed_id) {
        $scope.feed.feed_id = resp.data.feed_id;
      } else {
        window.alert('There was an error saving that feed.');
      }
      updateLoader.stop();
    }).error(updateLoader.stop);

    return false;
  };

  $scope.deleteFeed = function () {
    var sure = window.confirm('Are you sure you want to delete this feed?');
    if (!sure) {
      return;
    }

    ApiClient.delete({
      url: 'feeds/' + $scope.feed.feed_id
    }).success(function () {
      $scope.feed = DEFAULT_FEED_OBJ;
      delete $scope.published_entries;
      delete $scope.unpublished_entries;
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
