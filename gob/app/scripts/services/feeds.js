'use strict';

angular.module('pourOver').factory('Feeds', ['$q', '$rootScope', 'ApiClient', function ($q, $rootScope, ApiClient) {

  var DEFAULT_FEED_OBJ = {
    feed_type: 1,
    max_stories_per_period: 1,
    schedule_period: 1,
    format_mode: 1,
    include_thumb: true,
    include_video: true
  };

  $rootScope.feed = _.extend({}, DEFAULT_FEED_OBJ);
  $rootScope.feeds = [];
  var selected_feed = false;
  var new_feed = false;

  var updateFeeds = function () {
    ApiClient.get({
      url: 'feeds'
    }).success(function (resp) {
      if (resp.data && resp.data.length) {
        $rootScope.feeds = resp.data;
        if (new_feed) {
          new_feed = false;
          return;
        }
        if (!selected_feed) {
          $rootScope.feed = resp.data[0];
        } else {
          _.each($rootScope.feeds, function (item) {
            if (item.feed_id === selected_feed.feed_id && item.feed_type === selected_feed.feed_type) {
              $rootScope.feed = item;
            }
          });
          selected_feed = false;
        }
      }
    });
  };

  updateFeeds();

  return {
    DEFAULT_FEED_OBJ: DEFAULT_FEED_OBJ,
    serialize_feed: function (feed) {
      _.each(['linked_list_mode', 'include_thumb', 'include_summary', 'include_video'], function (el) {
        if (!feed[el]) {
          delete feed[el];
        }
      });
      return feed;
    },
    setFeed: function (feed) {
      selected_feed = feed;
      console.log(feed);
      console.log($rootScope.feeds);
      _.each($rootScope.feeds, function (item) {
        if (item.feed_id === selected_feed.feed_id && item.feed_type === selected_feed.feed_type) {
          $rootScope.feed = item;
        }
      });
    },
    setNewFeed: function () {
      new_feed = true;
      $rootScope.feed = _.extend({}, DEFAULT_FEED_OBJ);
    },
    validateFeed: function (feed) {
      var deferred = $q.defer();
      var _this = this;
      ApiClient.post({
        url: 'feeds/validate',
        data: _this.serialize_feed(feed)
      }).success(function (resp) {
        if (resp.status === 'ok') {
          deferred.resolve(resp.data);
          return;
        }
        deferred.reject();
      }).error(deferred.reject);

      return deferred.promise;
    },
    createFeed: function (feed) {
      var deferred = $q.defer();
      var _this = this;
      ApiClient.post({
        url: 'feeds',
        data: _this.serialize_feed(feed)
      }).success(function (resp) {
        if (resp.data && resp.data.feed_id) {
          feed.feed_id = resp.data.feed_id;
          _this.updateFeeds();
          deferred.resolve(resp.data);
        } else {
          deferred.reject();
        }
      }, deferred.reject);

      return deferred.promise;
    },
    updateFeed: function (feed) {
      var deferred = $q.defer();
      var _this = this;
      ApiClient.post({
        url: 'feeds/' + feed.feed_type + '/' + feed.feed_id,
        data: _this.serialize_feed(feed)
      }).success(function (resp) {
        if (resp.data && resp.data.feed_id) {
          selected_feed = feed.feed_id;
          _this.updateFeeds();
        } else {
          deferred.reject();
        }
        deferred.resolve();
      }, deferred.reject);

      return deferred.promise;
    },
    deleteFeed: function (feed_type, feed_id) {
      var deferred = $q.defer();

      ApiClient.delete({
        url: 'feeds/' + feed_type + '/' + feed_id
      }).success(function () {
        $rootScope.feeds = _.filter($rootScope.feeds, function (item) {
          return item.feed_id !== feed_id;
        });
        deferred.resolve();
      });

      return deferred.promise;
    },
    updateFeeds: updateFeeds
  };

}]);